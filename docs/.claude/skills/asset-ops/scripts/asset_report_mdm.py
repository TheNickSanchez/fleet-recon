#!/usr/bin/env python3
"""Step 2 — add MDM enrollment status, respective to each device's platform.

macOS rows are resolved against Jamf, Windows rows against Intune, dispatching on
the Platform column that step 1 already derived from ServiceNow model metadata.

    passkey run jamf_api -- passkey run intune -- \
      .venv/bin/python scripts/asset_report_mdm.py

Adds: MDM, MDM Status, MDM Last Check-In, MDM Detail. Re-running overwrites those
four columns in place rather than appending duplicates.

Jamf reads are batched 40 serials per call, so the macOS side costs ~1 call per 40
devices. Intune has no bulk serial filter, so Windows costs 1 call per device and
is threaded.
"""

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fleet_common import (
    DEFAULT_REPORT,
    INTUNE_ENV,
    JAMF_ENV,
    IntuneSession,
    JamfSession,
    breakdown,
    chunk_list,
    load_report,
    lookup_rows,
    require_env,
    set_columns,
    skip_reason,
    stale_warning,
    write_report,
    write_summary_json,
)

MDM_COLUMNS = ["MDM", "MDM Status", "MDM Last Check-In", "MDM Detail"]


def jamf_pass(session, rows, batch_size):
    """Batch-resolve macOS serials. Returns {row index: column values}."""
    out = {}
    # A serial can appear on more than one row (shared or reassigned asset), so map
    # each serial to every row index that wants it — a plain dict would drop rows.
    indexes = {}
    for row in rows:
        indexes.setdefault(row["Serial"], []).append(row["index"])
    serials = sorted(indexes)
    total = (len(serials) + batch_size - 1) // batch_size

    def assign(serial, values):
        for index in indexes[serial]:
            out[index] = values

    for n, chunk in enumerate(chunk_list(serials, batch_size), 1):
        print(f"[*] Jamf batch {n}/{total} ({len(chunk)} serials)...")
        try:
            found = session.inventory_batch(chunk, ("GENERAL", "HARDWARE"))
        except Exception as exc:
            detail = str(exc)[:120]
            if "400" in detail:
                detail += "  (try --batch-size 20)"
            for serial in chunk:
                assign(serial, {
                    "MDM": "Jamf", "MDM Status": "Lookup Error",
                    "MDM Last Check-In": "", "MDM Detail": detail,
                })
            continue

        for serial in chunk:
            record = found.get(serial)
            if not record:
                assign(serial, {
                    "MDM": "Not Found", "MDM Status": "Not Found in Jamf",
                    "MDM Last Check-In": "", "MDM Detail": "no Jamf inventory record",
                })
                continue
            general = record.get("general") or {}
            managed = ((general.get("remoteManagement") or {}).get("managed"))
            last_contact = str(general.get("lastContactTime") or "")
            assign(serial, {
                "MDM": "Jamf",
                # Present-but-unmanaged is a different remediation path from absent.
                "MDM Status": "Managed" if managed else "Unmanaged",
                "MDM Last Check-In": last_contact[:10],
                "MDM Detail": str(general.get("name") or ""),
            })
    return out


def intune_one(session, row):
    serial, index = row["Serial"], row["index"]
    try:
        device = session.find_device_by_serial(serial)
    except Exception as exc:
        return index, {"MDM": "Intune", "MDM Status": "Lookup Error",
                       "MDM Last Check-In": "", "MDM Detail": str(exc)[:120]}
    if not device:
        return index, {"MDM": "Not Found", "MDM Status": "Not Found in Intune",
                       "MDM Last Check-In": "", "MDM Detail": "no Intune managed-device record"}
    compliance = str(device.get("complianceState") or "")
    return index, {
        "MDM": "Intune",
        "MDM Status": "Managed",
        "MDM Last Check-In": str(device.get("lastSyncDateTime") or "")[:10],
        "MDM Detail": f"compliance={compliance or 'unknown'}; "
                      f"agent={device.get('managementAgent') or 'unknown'}",
    }


def intune_pass(session, rows, workers):
    out = {}
    print(f"[*] Checking {len(rows)} Windows device(s) in Intune ({workers} workers)...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(intune_one, session, row) for row in rows]
        for done, future in enumerate(as_completed(futures), 1):
            index, values = future.result()
            out[index] = values
            if done % 25 == 0 or done == len(rows):
                print(f"    {done}/{len(rows)} checked...")
    return out


def main():
    parser = argparse.ArgumentParser(description="Add platform-respective MDM status columns.")
    parser.add_argument("--location", default=DEFAULT_REPORT, help=f"Report CSV (default: {DEFAULT_REPORT}).")
    parser.add_argument("--batch-size", type=int, default=40,
                        help="Jamf serials per inventory call (default: 40; drop to 20 on HTTP 400).")
    parser.add_argument("--workers", type=int, default=10, help="Intune concurrency (default: 10).")
    parser.add_argument("--max-age-hours", type=float, default=24.0,
                        help="Warn if the report is older than this (default: 24).")
    parser.add_argument("--summary-json", default="", help="Append one JSONL telemetry object per run.")
    args = parser.parse_args()

    df = load_report(args.location)
    stale_warning(args.location, args.max_age_hours)
    rows, skipped = lookup_rows(df)

    macos = [r for r in rows if r["Platform"] == "macOS"]
    windows = [r for r in rows if r["Platform"] == "Windows"]
    if not rows:
        print("[!] No rows with a resolvable serial — nothing to check.")
        return

    if macos:
        require_env(JAMF_ENV, "jamf_api")
    if windows:
        require_env(INTUNE_ENV, "intune")

    started = time.time()
    results, calls = {}, {}

    if macos:
        jamf = JamfSession()
        results.update(jamf_pass(jamf, macos, args.batch_size))
        calls["jamf"] = dict(jamf.calls)
    if windows:
        intune = IntuneSession()
        results.update(intune_pass(intune, windows, args.workers))
        calls["intune"] = dict(intune.calls)

    # Rows we never looked up get an explicit reason, never a silent blank.
    for row_index in df.index:
        if row_index not in results:
            reason = skip_reason(str(df.at[row_index, "Platform"]).strip(),
                                 df.at[row_index, "Serial"])
            results[row_index] = {"MDM": reason, "MDM Status": reason,
                                  "MDM Last Check-In": "", "MDM Detail": ""}

    df = set_columns(df, results, MDM_COLUMNS)
    write_report(df, args.location)

    checked = df[df["MDM"].isin(("Jamf", "Intune", "Not Found"))]
    statuses = checked["MDM Status"].tolist()
    print(f"\n[+] {args.location} — MDM columns added for {len(checked)} device(s)")
    print(f"    MDM:    {breakdown(checked['MDM'].tolist())}")
    print(f"    Status: {breakdown(statuses)}")
    if skipped:
        print(f"    Skipped: {breakdown([k for k, v in skipped.items() for _ in range(v)])}")

    for platform, subset, label in (("macOS", macos, "Jamf"), ("Windows", windows, "Intune")):
        if not subset:
            continue
        missing = sum(1 for r in subset if results.get(r["index"], {}).get("MDM Status") == f"Not Found in {label}")
        if missing / len(subset) > 0.20:
            print(f"[!] {missing}/{len(subset)} {platform} devices not found in {label} (>20%) — "
                  "enrollment data-quality gap, not a script fault.")

    print(f"[i] calls: {calls}  duration={time.time() - started:.1f}s")
    write_summary_json(args.summary_json, {
        "step": "mdm", "report": args.location,
        "counts": {"macos": len(macos), "windows": len(windows),
                   "checked": len(checked), "skipped": skipped},
        "calls": calls, "duration_s": round(time.time() - started, 2),
    })


if __name__ == "__main__":
    main()
