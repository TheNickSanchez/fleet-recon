#!/usr/bin/env python3
"""Step 1.5 (optional) — fill in "No Device Assigned" rows using an MDM reverse
lookup, so the rest of the pipeline sees a real device instead of a gap.

ServiceNow "No Device Assigned" means the asset record has nothing linked to the
user — it does NOT mean the user has no device. This step takes reverse-lookup
results for exactly that cohort and writes them into the SAME Serial / Platform /
Model columns step 1 uses, rather than a parallel set of "MDM ..." columns — a
device found this way isn't a different kind of fact, it's the same fact step 1
would have produced if ServiceNow's record had been complete. `Notes` carries the
one-line provenance ("not in ServiceNow — found via jamf") since that's the only
part that's genuinely different.

Run this BEFORE step 3 (app discovery) — a row only gets checked for an app if it
already has a real Serial + Platform, so filling gaps after the app step (as an
earlier version of this script did) means those rows get skipped rather than
looked up. Order is: build (step 1) -> this step -> app discovery (step 3).

The lookup itself is NOT done here: it requires the Jamf (`jamf_get_user_devices`)
and Intune (`intune_lookup_users`) MCP tools, which a plain Python script has no
access to. The agent runs those lookups for every "No Device Assigned" username,
batching Intune (one call, comma-separated usernames) and Jamf (one call per user,
run in parallel) per CLAUDE.md's "always batch independent MCP reads" rule, then
writes a findings JSON and calls this script to merge it in:

    .venv/bin/python scripts/asset_report_snow_gap.py \
      --findings input/output/snow_gap_findings.json

findings JSON shape:
    {"<username>": {"found": bool, "source": "jamf"|"intune"|"none",
                     "serial": str, "platform": str, "model": str,
                     "last_check_in": str}}

Re-running overwrites Serial/Platform/Model/Notes on the same "No Device
Assigned" rows in place — idempotent, same as every other step here. Only rows
whose Platform is still "No Device Assigned" are touched; once filled, a row
looks like any other device row and a re-run leaves it alone.
"""

import argparse
import json

from fleet_common import DEFAULT_REPORT, load_report, write_report

TARGET_PLATFORM = "No Device Assigned"


def main():
    parser = argparse.ArgumentParser(
        description='Fill "No Device Assigned" rows from an MDM reverse-lookup.'
    )
    parser.add_argument("--findings", required=True, help="Path to the reverse-lookup findings JSON.")
    parser.add_argument("--report", default=DEFAULT_REPORT, help=f"Report to update (default: {DEFAULT_REPORT}).")
    args = parser.parse_args()

    df = load_report(args.report, required=("Username", "Platform", "Serial"))
    with open(args.findings) as fh:
        findings = json.load(fh)

    target_idx = df.index[df["Platform"] == TARGET_PLATFORM]
    filled, confirmed_none, missing = [], [], []
    for idx in target_idx:
        username = df.at[idx, "Username"]
        info = findings.get(username)
        if info is None:
            missing.append(username)
            continue
        if info.get("found"):
            df.at[idx, "Serial"] = str(info.get("serial", "")).upper()
            df.at[idx, "Platform"] = info.get("platform", "")
            df.at[idx, "Model"] = info.get("model", "")
            df.at[idx, "Notes"] = f"not in ServiceNow — found via {info.get('source', 'mdm')}"
            filled.append((username, info.get("source", ""), info.get("platform", ""), info.get("serial", "")))
        else:
            df.at[idx, "Notes"] = "confirmed no active device (checked jamf/intune)"
            confirmed_none.append(username)

    write_report(df, args.report)

    checked = len(target_idx) - len(missing)
    print(f"\n[+] {args.report} — checked {checked}/{len(target_idx)} 'No Device Assigned' user(s)")
    if filled:
        print(f"[!] {len(filled)} row(s) filled in from an MDM ServiceNow doesn't know about "
              "— these now flow through app discovery like any other device:")
        for username, source, platform, serial in filled:
            print(f"    {username:24} {source:8} {platform:8} {serial}")
    if confirmed_none:
        print(f"[i] {len(confirmed_none)} user(s) confirmed device-less in both Jamf and Intune.")
    if missing:
        print(f"[!] {len(missing)} user(s) had no lookup result in the findings file: {', '.join(missing)}")


if __name__ == "__main__":
    main()
