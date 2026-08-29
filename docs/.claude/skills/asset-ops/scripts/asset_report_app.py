#!/usr/bin/env python3
"""Step 3 — add per-app install/health columns, respective to each platform.

macOS resolves the app against a Jamf extension attribute first, because EAs carry
diagnostic nuance a bare install check can't ("ERROR - Installed (Not Enrolled)").
Only when no EA matches does it fall back to Jamf's installed-applications
inventory. Windows uses Intune's Managed Apps intent/state.

    passkey run jamf_api -- passkey run intune -- \
      .venv/bin/python scripts/asset_report_app.py --app Zscaler

Adds three columns per app: "<App> Status" (raw), "<App> Health" (healthy /
unhealthy / unknown), and "<App> Source" (provenance). Run it again with a
different --app to add another set alongside; re-running the same app overwrites.

EA names are matched on a dash- and case-normalized form because Jamf mixes
hyphens and en-dashes across attribute names.
"""

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml

from fleet_common import (
    DEFAULT_REPORT,
    INTUNE_ENV,
    JAMF_ENV,
    IntuneSession,
    JamfSession,
    breakdown,
    chunk_list,
    extension_attributes,
    load_report,
    lookup_rows,
    normalize_label,
    require_env,
    set_columns,
    skip_reason,
    stale_warning,
    write_report,
    write_summary_json,
)

SIGNAL_MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_signal_map.yaml")

STATE_PRIORITY = ["installed", "failed", "notApplicable", "unknown"]

# Fallback classifier when the app has no entry in app_signal_map.yaml.
GENERIC_HEALTHY = ["ok", "installed", "enrolled", "connected", "enabled", "running", "healthy"]
GENERIC_UNHEALTHY = ["error", "not installed", "not enrolled", "not running", "missing",
                     "disabled", "failed", "requires update", "not found"]


def load_rules(app):
    """Optional per-app overrides. Absent file or absent entry is fine."""
    if not os.path.exists(SIGNAL_MAP):
        return {}
    with open(SIGNAL_MAP) as fh:
        data = yaml.safe_load(fh) or {}
    token = normalize_label(app)
    for rule in data.get("statuses", []):
        names = [rule.get("key", ""), rule.get("label", "")]
        if any(normalize_label(n) == token for n in names if n):
            return rule
    return {}


def classify(value, rules):
    """Collapse a raw status string to healthy / unhealthy / unknown."""
    text = normalize_label(value)
    if not text:
        return "unknown"
    unhealthy = [normalize_label(t) for t in rules.get("unhealthy_contains", GENERIC_UNHEALTHY)]
    healthy = [normalize_label(t) for t in rules.get("healthy_contains", GENERIC_HEALTHY)]
    # Unhealthy wins: "ERROR - installed (...)" contains both signals.
    if any(t in text for t in unhealthy):
        return "unhealthy"
    if any(t in text for t in healthy):
        return "healthy"
    return "unknown"


def resolve_ea_name(app, ea_names, rules):
    """Pick the EA that reports on this app, from the names Jamf actually returned.

    Resolved at runtime rather than hardcoded — the EA namespace is large and
    changes, and an override in app_signal_map.yaml wins when a name is ambiguous.
    """
    for path in rules.get("paths", []):
        wanted = normalize_label(str(path).split(".", 1)[-1])
        for name in ea_names:
            if normalize_label(name) == wanted:
                return name, []
    token = normalize_label(app)
    matches = [n for n in ea_names if token in normalize_label(n)]
    if not matches:
        return None, []
    # Prefer the shortest match: "Compliance - Slack" over "Compliance - Slack Helper".
    matches.sort(key=lambda n: (len(n), n))
    return matches[0], matches[1:]


def jamf_pass(session, rows, app, rules, batch_size, cols):
    """EA-first, inventory-fallback resolution across macOS rows."""
    out = {}
    # A serial can appear on more than one row (shared or reassigned asset), so map
    # each serial to every row index that wants it — a plain dict would drop rows.
    indexes = {}
    for row in rows:
        indexes.setdefault(row["Serial"], []).append(row["index"])
    serials = sorted(indexes)
    total = (len(serials) + batch_size - 1) // batch_size
    ea_name, ambiguous = None, []
    resolved = False
    needs_fallback = []

    def assign(serial, values):
        for index in indexes[serial]:
            out[index] = values

    for n, chunk in enumerate(chunk_list(serials, batch_size), 1):
        print(f"[*] Jamf batch {n}/{total} ({len(chunk)} serials)...")
        try:
            found = session.inventory_batch(chunk, ("GENERAL", "HARDWARE", "EXTENSION_ATTRIBUTES"))
        except Exception as exc:
            detail = str(exc)[:120]
            if "400" in detail:
                detail += "  (try --batch-size 20)"
            for serial in chunk:
                assign(serial, dict(zip(cols, ("Lookup Error", "unknown", detail))))
            continue

        for serial in chunk:
            record = found.get(serial)
            if not record:
                assign(serial, dict(zip(cols, ("Not Found in Jamf", "unknown", "none"))))
                continue
            attrs = extension_attributes(record)
            if not resolved and attrs:
                # Harvest EA names from the payloads we already fetched — no extra call.
                ea_name, ambiguous = resolve_ea_name(app, list(attrs), rules)
                resolved = True
                if ea_name:
                    print(f"[i] Matched extension attribute: {ea_name!r}")
                    if ambiguous:
                        print(f"[!] Also matched {len(ambiguous)}: {', '.join(ambiguous[:4])} — "
                              f"add an override to app_signal_map.yaml to pin one.")
                else:
                    print(f"[i] No extension attribute matches {app!r} — "
                          "falling back to Jamf application inventory.")
            value = attrs.get(ea_name, "") if ea_name else ""
            if ea_name and str(value).strip():
                assign(serial, dict(zip(cols, (value, classify(value, rules), f"ea:{ea_name}"))))
            else:
                needs_fallback.append((serial, record.get("id")))

    if needs_fallback:
        for serial, values in inventory_fallback(session, needs_fallback, app, rules, cols).items():
            assign(serial, values)
    return out


def inventory_fallback(session, targets, app, rules, cols):
    """Per-device APPLICATIONS read for devices with no usable EA value.

    Returns {SERIAL: column values}.
    """
    out = {}
    print(f"[*] Application-inventory fallback for {len(targets)} device(s)...")
    token = normalize_label(app)
    for serial, jamf_id in targets:
        if not jamf_id:
            out[serial] = dict(zip(cols, ("No Signal Mapped", "unknown", "none")))
            continue
        try:
            data = session.get(
                f"{session.base}/api/v1/computers-inventory-detail/{jamf_id}",
                params=[("section", "APPLICATIONS")], counter="detail",
            )
            apps = data.get("applications") or []
        except Exception as exc:
            out[serial] = dict(zip(cols, ("Lookup Error", "unknown", str(exc)[:120])))
            continue
        hits = [a for a in apps if token in normalize_label(a.get("name"))]
        if hits:
            versions = ", ".join(sorted({str(a.get("version") or "?") for a in hits}))
            status = f"installed ({versions})"
        else:
            status = "not installed"
        out[serial] = dict(zip(cols, (status, classify(status, rules), "jamf-inventory")))
    return out


def intune_one(session, row, app, rules, cols):
    index, serial = row["index"], row["Serial"]
    token = normalize_label(app)
    try:
        device = session.find_device_by_serial(serial)
    except Exception as exc:
        return index, dict(zip(cols, ("Lookup Error", "unknown", str(exc)[:120])))
    if not device:
        return index, dict(zip(cols, ("Not Found in Intune", "unknown", "none")))
    user_id = device.get("userId")
    if not user_id:
        return index, dict(zip(cols, ("No Assigned User", "unknown", "intune-managed-apps")))
    try:
        apps = session.managed_app_states(user_id, device.get("id"))
    except Exception as exc:
        return index, dict(zip(cols, ("Lookup Error", "unknown", str(exc)[:120])))

    matches = [a for a in apps if token in normalize_label(a.get("displayName"))]
    if not matches:
        return index, dict(zip(cols, ("not installed", "unhealthy", "intune-managed-apps")))
    states = {str(a.get("installState") or "") for a in matches}
    status = next((s for s in STATE_PRIORITY if s in states), next(iter(states)))
    # Companion installers often sit at 'unknown' forever; keep them visible in Source.
    detail = "; ".join(sorted(f"{a.get('displayName')}:{a.get('installState')}" for a in matches))
    return index, dict(zip(cols, (status, classify(status, rules), f"intune-managed-apps ({detail})"[:240])))


def intune_pass(session, rows, app, rules, workers, cols):
    out = {}
    print(f"[*] Checking {len(rows)} Windows device(s) in Intune ({workers} workers)...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(intune_one, session, r, app, rules, cols) for r in rows]
        for done, future in enumerate(as_completed(futures), 1):
            index, values = future.result()
            out[index] = values
            if done % 25 == 0 or done == len(rows):
                print(f"    {done}/{len(rows)} checked...")
    return out


def main():
    parser = argparse.ArgumentParser(description="Add per-app install/health columns.")
    parser.add_argument("--app", required=True, help='App name, e.g. "Zscaler" or "Slack".')
    parser.add_argument("--location", default=DEFAULT_REPORT, help=f"Report CSV (default: {DEFAULT_REPORT}).")
    parser.add_argument("--batch-size", type=int, default=40,
                        help="Jamf serials per inventory call (default: 40; drop to 20 on HTTP 400).")
    parser.add_argument("--workers", type=int, default=10, help="Intune concurrency (default: 10).")
    parser.add_argument("--max-age-hours", type=float, default=24.0,
                        help="Warn if the report is older than this (default: 24).")
    parser.add_argument("--summary-json", default="", help="Append one JSONL telemetry object per run.")
    args = parser.parse_args()

    app = args.app.strip()
    label = app if app else "App"
    cols = [f"{label} Status", f"{label} Health", f"{label} Source"]

    df = load_report(args.location)
    stale_warning(args.location, args.max_age_hours)
    rows, skipped = lookup_rows(df)
    macos = [r for r in rows if r["Platform"] == "macOS"]
    windows = [r for r in rows if r["Platform"] == "Windows"]
    if not rows:
        print("[!] No rows with a resolvable serial — nothing to check.")
        return

    rules = load_rules(app)
    if rules:
        print(f"[i] Using override rules for {rules.get('label') or rules.get('key')} from app_signal_map.yaml")
    if macos:
        require_env(JAMF_ENV, "jamf_api")
    if windows:
        require_env(INTUNE_ENV, "intune")

    started = time.time()
    results, calls = {}, {}

    if macos:
        jamf = JamfSession()
        results.update(jamf_pass(jamf, macos, app, rules, args.batch_size, cols))
        calls["jamf"] = dict(jamf.calls)
    if windows:
        intune = IntuneSession()
        results.update(intune_pass(intune, windows, app, rules, args.workers, cols))
        calls["intune"] = dict(intune.calls)

    for row_index in df.index:
        if row_index not in results:
            reason = skip_reason(str(df.at[row_index, "Platform"]).strip(),
                                 df.at[row_index, "Serial"])
            results[row_index] = dict(zip(cols, (reason, "unknown", "none")))

    df = set_columns(df, results, cols)
    write_report(df, args.location)

    checked = df[~df[cols[0]].str.startswith("Skipped")]
    print(f"\n[+] {args.location} — {label} columns added for {len(checked)} device(s)")
    print(f"    Status: {breakdown(checked[cols[0]].tolist(), top=8)}")
    print(f"    Health: {breakdown(checked[cols[1]].tolist())}")
    print(f"    Source: {breakdown([s.split(' (')[0] for s in checked[cols[2]].tolist()])}")

    attention = checked[checked[cols[1]] != "healthy"]
    if len(attention):
        print(f"\n[!] {len(attention)} device(s) need attention:")
        for _, row in attention.head(25).iterrows():
            print(f"    {row['Username']:28} {row['Serial']:14} {row['Platform']:8} {row[cols[0]][:60]}")
        if len(attention) > 25:
            print(f"    ... and {len(attention) - 25} more — see {args.location}")

    print(f"[i] calls: {calls}  duration={time.time() - started:.1f}s")
    write_summary_json(args.summary_json, {
        "step": "app", "app": app, "report": args.location,
        "counts": {"macos": len(macos), "windows": len(windows),
                   "checked": len(checked), "attention": len(attention), "skipped": skipped},
        "calls": calls, "duration_s": round(time.time() - started, 2),
    })


if __name__ == "__main__":
    main()
