#!/usr/bin/env python3
"""Step 1 — build the device-grained asset report from a user list.

Resolves each username/email to its ServiceNow hardware and writes ONE ROW PER
DEVICE. A user with three assets produces three rows; a user with none still
produces one row so nothing from the input list is silently dropped.

    passkey run servicenow -- .venv/bin/python scripts/asset_report_build.py \
      --location "input/example.csv"

This emits a flat schema with no ';'-joined parallel columns -- one row per
device, plus the ServiceNow State/Substate fields. Substate is what carries
Primary vs Secondary for multi-device users. The old user_hardware_lookup.py
(one row per user, ';'-joined multi-serial columns) no longer exists: every
script that used to consume that shape (jamf_group_sync.py, intune_app_lookup.py)
now reads this device-grained report instead.
"""

import argparse
import os
import sys
import time

import pandas as pd
import requests

from fleet_common import (
    BASE_COLUMNS,
    DEFAULT_REPORT,
    PLATFORM_ORDER,
    breakdown,
    chunk_list,
    is_real_serial,
    require_env,
    write_report,
    write_summary_json,
)

SNOW_ENV = ("SNOW_HOST", "SNOW_USERNAME", "SNOW_PASSWORD")
DOMAIN = "@docusign.com"
BATCH = 50

USERNAME_CANDIDATES = ("usernames", "username", "email", "user email", "user_email")

HARDWARE_FIELDS = (
    "assigned_to,serial_number,model.name,model.manufacturer.name,"
    "install_status,substatus,asset_tag"
)


def detect_username_column(df):
    for col in df.columns:
        if str(col).strip().casefold() in USERNAME_CANDIDATES:
            return col
    raise KeyError(
        f"Could not find a username/email column. Got: {list(df.columns)}. "
        "Rename the header to 'Usernames' and re-run."
    )


def normalize_username(value):
    return str(value or "").strip().casefold().split("@")[0]


def derive_platform(model_name, manufacturer):
    """Authoritative platform, from ServiceNow model metadata.

    Never infer platform from serial-number prefixes — get_fleet_encryption_status.py
    does that and it misclassifies anything outside its prefix list.
    """
    model = str(model_name or "").casefold()
    maker = str(manufacturer or "").casefold()

    # Model-keyword checks run BEFORE the manufacturer lists, because several vendors
    # build for more than one OS: Apple makes Macs and iPads, Samsung makes Android
    # tablets and Windows laptops. Manufacturer alone would misroute those.
    if any(m in model for m in ("virtual desktop", "parallels", "workspace", "virtual server")):
        return "Virtual Desktop"
    if any(m in model for m in ("ipad", "iphone", "ipod", "apple tv", "apple watch")):
        return "iOS/iPadOS"
    if "chromebook" in model or "chromeos" in model or "chrome os" in model:
        return "ChromeOS"
    if any(m in model for m in ("galaxy s", "galaxy note", "galaxy tab", "galaxy a",
                                "pixel", "nexus", "moto ", "oneplus")):
        return "Android"
    if "apple" in maker or "mac" in model:
        return "macOS"
    # Includes the vendors beyond the big three that turn up in ServiceNow — an Acer
    # or MSI laptop left as Unknown gets skipped from Intune entirely, which reads as
    # "not checked" when the device is in fact enrolled.
    if any(m in maker for m in ("dell", "lenovo", "hp", "hewlett", "microsoft", "acer",
                                "msi", "asus", "samsung", "toshiba", "fujitsu",
                                "panasonic", "razer", "gigabyte", "getac")):
        return "Windows"
    return "Unknown"


def dv(field):
    """Read a sysparm_display_value=all field: prefer display text, fall back to value."""
    if isinstance(field, dict):
        return str(field.get("display_value") or field.get("value") or "").strip()
    return str(field or "").strip()


def raw(field):
    if isinstance(field, dict):
        return str(field.get("value") or "").strip()
    return str(field or "").strip()


def snow_get(session, host, table, params):
    resp = session.get(
        f"{host}/api/now/table/{table}",
        params={**params, "sysparm_display_value": "all"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def fetch_users(session, host, usernames, calls):
    """{sys_id: username} for every input user ServiceNow recognises."""
    found = {}
    emails = [u + DOMAIN for u in usernames]
    total = (len(emails) + BATCH - 1) // BATCH
    for i, chunk in enumerate(chunk_list(emails, BATCH), 1):
        print(f"[*] Resolving users, batch {i}/{total}...")
        rows = snow_get(
            session, host, "sys_user",
            {"sysparm_query": "emailIN" + ",".join(chunk), "sysparm_fields": "sys_id,email"},
        )
        calls["snow_user"] += 1
        for row in rows:
            sys_id = raw(row.get("sys_id"))
            email = dv(row.get("email")).casefold()
            if sys_id and email:
                found[sys_id] = email.split("@")[0]
    return found


def fetch_hardware(session, host, sys_ids, calls, states):
    """{sys_id: [device dicts]} for all assigned hardware.

    The install_status filter is applied client-side on the display value so
    callers can pass human state names ("In use") without knowing the numeric codes.
    """
    by_user = {}
    total = (len(sys_ids) + BATCH - 1) // BATCH
    for i, chunk in enumerate(chunk_list(sys_ids, BATCH), 1):
        print(f"[*] Fetching hardware, batch {i}/{total}...")
        rows = snow_get(
            session, host, "alm_hardware",
            {
                "sysparm_query": "assigned_toIN" + ",".join(chunk),
                "sysparm_fields": HARDWARE_FIELDS,
            },
        )
        calls["snow_hardware"] += 1
        for row in rows:
            state = dv(row.get("install_status"))
            if states and state.casefold() not in states:
                continue
            owner = raw(row.get("assigned_to"))
            if not owner:
                continue
            by_user.setdefault(owner, []).append(
                {
                    "serial": dv(row.get("serial_number")).upper(),
                    "model": dv(row.get("model.name")),
                    "maker": dv(row.get("model.manufacturer.name")),
                    "state": state,
                    "substate": dv(row.get("substatus")),
                    "asset_tag": dv(row.get("asset_tag")),
                }
            )
    return by_user


def build_rows(usernames, users_by_sys_id, hardware, platforms=None):
    """One row per device; one placeholder row per user with no device.

    `platforms`, if given, is an allow-list of derived Platform values (e.g.
    {"macOS", "Windows"}). A user whose only hardware falls outside it is
    counted in `platform_only_skips` rather than emitted as "No Device
    Assigned" — they do have a device, it's just out of scope for this list,
    which is a different fact than having none.
    """
    sys_ids_by_username = {}
    for sys_id, username in users_by_sys_id.items():
        sys_ids_by_username.setdefault(username, []).append(sys_id)

    rows = []
    platform_only_skips = 0
    for username in usernames:
        sys_ids = sys_ids_by_username.get(username)
        if not sys_ids:
            rows.append({**dict.fromkeys(BASE_COLUMNS, ""), "Username": username,
                         "Platform": "Not Found in SN", "Notes": "user not in ServiceNow"})
            continue
        devices = [d for sid in sys_ids for d in hardware.get(sid, [])]
        if not devices:
            rows.append({**dict.fromkeys(BASE_COLUMNS, ""), "Username": username,
                         "Platform": "No Device Assigned", "Notes": "no hardware assigned"})
            continue
        if platforms is not None:
            devices = [d for d in devices if derive_platform(d["model"], d["maker"]) in platforms]
            if not devices:
                platform_only_skips += 1
                continue
        for n, device in enumerate(devices, 1):
            rows.append(
                {
                    "Username": username,
                    "Serial": device["serial"],
                    "Platform": derive_platform(device["model"], device["maker"]),
                    "State": device["state"],
                    "Substate": device["substate"],
                    "Model": device["model"],
                    "Asset Tag": device["asset_tag"],
                    "Notes": f"device {n} of {len(devices)}" if len(devices) > 1 else "",
                }
            )
    rows.sort(key=lambda r: (PLATFORM_ORDER.get(r["Platform"], 9), r["Username"]))
    return rows, platform_only_skips


def main():
    parser = argparse.ArgumentParser(description="Build the device-grained asset report.")
    parser.add_argument("--location", required=True, help="Input CSV with a username/email column.")
    parser.add_argument("--output", default=DEFAULT_REPORT, help=f"Output CSV (default: {DEFAULT_REPORT}).")
    parser.add_argument("--states", default="",
                        help='Comma-separated ServiceNow states to keep, e.g. "In use,In stock". '
                             "Default: all states.")
    parser.add_argument("--platforms", default="",
                        help='Comma-separated Platform allow-list, e.g. "macOS,Windows". Drops '
                             "iPads/Android/ChromeOS/Virtual Desktop/Unknown device rows entirely "
                             "instead of listing them as Skipped. Default: all platforms.")
    parser.add_argument("--summary-json", default="", help="Append one JSONL telemetry object per run.")
    args = parser.parse_args()

    require_env(SNOW_ENV, "servicenow")
    if not os.path.exists(args.location):
        print(f"[-] Input file not found: {args.location}")
        sys.exit(1)

    states = {s.strip().casefold() for s in args.states.split(",") if s.strip()}
    platforms = {p.strip() for p in args.platforms.split(",") if p.strip()} or None
    started = time.time()
    calls = {"snow_user": 0, "snow_hardware": 0}

    source = pd.read_csv(args.location, dtype=str).fillna("")
    column = detect_username_column(source)
    usernames = sorted({normalize_username(v) for v in source[column] if normalize_username(v)})
    print(f"[*] {len(usernames)} unique users from {os.path.basename(args.location)} (column '{column}')")

    host = os.environ["SNOW_HOST"].rstrip("/")
    session = requests.Session()
    session.auth = (os.environ["SNOW_USERNAME"], os.environ["SNOW_PASSWORD"])

    users_by_sys_id = fetch_users(session, host, usernames, calls)
    hardware = fetch_hardware(session, host, list(users_by_sys_id), calls, states)
    rows, platform_only_skips = build_rows(usernames, users_by_sys_id, hardware, platforms)

    df = pd.DataFrame(rows, columns=BASE_COLUMNS)
    write_report(df, args.output, columns=BASE_COLUMNS)

    platforms = df["Platform"].tolist()
    devices = df[~df["Platform"].isin(("No Device Assigned", "Not Found in SN"))]
    not_found = platforms.count("Not Found in SN")
    dupes = devices["Serial"].duplicated().sum()

    print(f"\n[+] {args.output} — {len(df)} rows ({len(usernames)} users, {len(devices)} devices)")
    print(f"    Platform: {breakdown(platforms)}")
    print(f"    State:    {breakdown(devices['State'].tolist())}")
    print(f"    Substate: {breakdown(devices['Substate'].tolist())}")
    if dupes:
        print(f"[!] {dupes} duplicate serial(s) — shared or reassigned assets, kept as separate rows.")
    if platforms is not None and platform_only_skips:
        print(f"[!] {platform_only_skips} user(s) have hardware but none in {{{', '.join(sorted(platforms))}}} "
              "— excluded entirely, not listed as 'No Device Assigned'.")
    placeholders = devices[~devices["Serial"].map(is_real_serial)]
    if len(placeholders):
        print(f"[!] {len(placeholders)} asset(s) with a placeholder serial — ServiceNow data entry, "
              "not an enrollment gap. Steps 2-3 skip them rather than reporting a false miss:")
        for _, row in placeholders.head(10).iterrows():
            print(f"    {row['Username']:28} {row['Serial']:12} {row['Model']}")
    if usernames and not_found / len(usernames) > 0.20:
        print(f"[!] {not_found}/{len(usernames)} users not found in ServiceNow (>20%) — "
              "check the input list format before relying on this report.")
    print(f"[i] calls: snow={sum(calls.values())}  duration={time.time() - started:.1f}s")

    write_summary_json(args.summary_json, {
        "step": "build", "source": args.location, "output": args.output,
        "states_filter": sorted(states) or "all",
        "platforms_filter": sorted(platforms) if platforms else "all",
        "counts": {"users": len(usernames), "rows": len(df), "devices": len(devices),
                   "not_found_in_sn": not_found, "duplicate_serials": int(dupes),
                   "platform_only_skips": platform_only_skips},
        "calls": calls, "duration_s": round(time.time() - started, 2),
    })


if __name__ == "__main__":
    main()
