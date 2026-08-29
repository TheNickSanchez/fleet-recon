"""Windows-only Managed Apps variant of asset-ops step 3.

    passkey run intune -- .venv/bin/python scripts/intune_app_lookup.py \
      --app "Zscaler" --workers 10

Reads the asset-ops pipeline's device-grained asset_report.csv (Serial/Platform
columns, one row per device already) and checks Intune's Managed Apps
intent/state data for a Windows-only target list -- more accurate for that case
than asset_report_app.py's default software-inventory signal. See SKILL.md's
"Windows-only Managed Apps variant of step 3" section for when to use this
instead of step 3 proper.
"""

import argparse
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from fleet_common import DEFAULT_REPORT, is_real_serial

TENANT_ID = os.environ.get("INTUNE_TENANT_ID", "")
CLIENT_ID = os.environ.get("INTUNE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("INTUNE_CLIENT_SECRET", "")

if not all([TENANT_ID, CLIENT_ID, CLIENT_SECRET]):
    print("[-] Missing credentials. Run via: passkey run intune -- .venv/bin/python scripts/intune_app_lookup.py --app <name>")
    sys.exit(1)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_BETA = "https://graph.microsoft.com/beta"

# Priority order when a device has multiple matching app entries (e.g. app + its
# certificate-installer companion) — pick the most informative single state to report.
STATE_PRIORITY = ["installed", "failed", "notApplicable", "unknown"]


class IntuneSession:
    """Token reuse + call counters, the same lightweight session pattern this
    skill's other scripts use for their Jamf/Intune clients."""

    def __init__(self):
        self.http = requests.Session()
        self.token = None
        self.refresh_at = 0.0
        self.lock = threading.Lock()
        self.calls = 0

    def _fetch_token(self):
        resp = self.http.post(
            f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "client_credentials",
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self.token = body["access_token"]
        expires_in = int(body.get("expires_in", 3600))
        self.refresh_at = time.time() + max(60, expires_in - 120)

    def _ensure_token(self):
        with self.lock:
            if not self.token or time.time() >= self.refresh_at:
                self._fetch_token()

    def get(self, url, **kwargs):
        self._ensure_token()
        with self.lock:
            self.calls += 1
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"
        resp = self.http.get(url, headers=headers, timeout=20, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def find_device_by_serial(self, serial):
        data = self.get(
            f"{GRAPH_BASE}/deviceManagement/managedDevices",
            params={"$filter": f"serialNumber eq '{serial}'"},
        )
        devices = data.get("value", [])
        return devices[0] if devices else None

    def get_managed_app_states(self, user_id, device_id):
        data = self.get(f"{GRAPH_BETA}/users/{user_id}/mobileAppIntentAndStates('{device_id}')")
        return data.get("mobileAppList", [])


def select_windows_rows(df: pd.DataFrame):
    """Windows-only device rows from asset_report.csv.

    asset_report.csv (scripts/asset_report_build.py) is already one row per
    device, so this is a straight Platform filter -- no ';'-joined Serial
    Number(s)/Platforms string to explode the way the old
    servicenow_hardware_report.csv shape required.
    """
    windows_rows = []
    skipped = {}

    for _, row in df.iterrows():
        platform = str(row.get("Platform", "")).strip() or "Unknown"
        serial = row.get("Serial", "")

        if platform != "Windows":
            skipped[platform] = skipped.get(platform, 0) + 1
            continue
        if not is_real_serial(serial):
            reason = "Skipped (placeholder serial)"
            skipped[reason] = skipped.get(reason, 0) + 1
            continue

        windows_rows.append({
            "Username": str(row.get("Username", "")).strip(),
            "Serial": str(serial).strip().upper(),
            "Model": str(row.get("Model", "")).strip(),
        })

    return windows_rows, skipped


def lookup_one(session: IntuneSession, row: dict, app_name: str):
    serial = row["Serial"]
    try:
        device = session.find_device_by_serial(serial)
    except Exception as e:
        return {**row, "status": "Lookup Error", "detail": str(e)[:120]}

    if not device:
        return {**row, "status": "Device Not Found in Intune", "detail": ""}

    user_id = device.get("userId")
    if not user_id:
        return {**row, "status": "No Assigned User", "detail": ""}

    try:
        apps = session.get_managed_app_states(user_id, device["id"])
    except Exception as e:
        return {**row, "status": "Lookup Error", "detail": str(e)[:120]}

    needle = app_name.lower()
    matches = [a for a in apps if needle in a.get("displayName", "").lower()]
    if not matches:
        return {**row, "status": "Not Found", "detail": ""}

    states = {a.get("installState", "unknown") for a in matches}
    status = next((s for s in STATE_PRIORITY if s in states), next(iter(states)))
    detail = "; ".join(sorted(f"{a.get('displayName')}:{a.get('installState')}" for a in matches))
    return {**row, "status": status, "detail": detail}


def main():
    parser = argparse.ArgumentParser(description="Check Intune Managed-Apps install status for an app across a list of Windows devices.")
    parser.add_argument("--location", default=DEFAULT_REPORT,
                         help=f"Asset report CSV from asset_report_build.py (default: {DEFAULT_REPORT})")
    parser.add_argument("--app", required=True, help="App name substring to check (e.g. 'Zscaler')")
    parser.add_argument("--output", default=None,
                         help="Output CSV path (default: input/output/windows_<app>_status.csv)")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent lookups (default: 8)")
    args = parser.parse_args()

    app_slug = "".join(c if c.isalnum() else "_" for c in args.app.lower()).strip("_")
    output_path = args.output or f"input/output/windows_{app_slug}_status.csv"

    print(f"[*] Reading: {args.location}")
    df = pd.read_csv(args.location, dtype=str).fillna("")
    df.columns = df.columns.str.strip()
    missing = [c for c in ("Serial", "Platform") if c not in df.columns]
    if missing:
        print(f"[-] {args.location} is missing required column(s): {', '.join(missing)}")
        print("    This script reads the asset-ops pipeline's asset_report.csv "
              "(scripts/asset_report_build.py), not a hardware-report CSV.")
        sys.exit(1)

    windows_rows, skipped = select_windows_rows(df)
    print(f"[+] {len(windows_rows)} Windows devices to check.")
    for platform, count in skipped.items():
        if count:
            label = "skipped (not supported by this Windows-only variant)" if platform not in ("Skipped (placeholder serial)",) else "skipped"
            print(f"    {count} {platform} device(s) {label}")

    windows_csv_path = "input/output/windows_devices.csv"
    os.makedirs(os.path.dirname(windows_csv_path), exist_ok=True)
    pd.DataFrame(windows_rows).to_csv(windows_csv_path, index=False)
    print(f"[+] Saved Windows device list: {windows_csv_path}")

    session = IntuneSession()
    results = []
    print(f"[*] Checking '{args.app}' across {len(windows_rows)} devices ({args.workers} workers)...")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(lookup_one, session, row, args.app): row for row in windows_rows}
        done = 0
        for future in as_completed(futures):
            results.append(future.result())
            done += 1
            if done % 25 == 0 or done == len(windows_rows):
                print(f"    {done}/{len(windows_rows)} checked...")

    status_col = f"{args.app} Status"
    out_df = pd.DataFrame(results).rename(columns={"status": status_col, "detail": f"{args.app} Detail"})
    out_df = out_df[["Username", "Serial", "Model", status_col, f"{args.app} Detail"]]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out_df.to_csv(output_path, index=False)

    from collections import Counter
    counts = Counter(r["status"] for r in results)
    print(f"\n[+] Saved: {output_path}")
    print(f"    Total Windows devices checked: {len(results)}")
    for status, count in counts.most_common():
        print(f"    {status:<28}: {count}")

    needs_attention = [r for r in results if r["status"] not in ("installed",)]
    if needs_attention:
        print(f"\n[!] {len(needs_attention)} device(s) need attention:")
        for r in needs_attention[:25]:
            print(f"    {r['Username']:<28} {r['Serial']:<14} {r['status']}")
        if len(needs_attention) > 25:
            print(f"    ... and {len(needs_attention) - 25} more — see {output_path}")
    print(f"\n[i] Graph API calls made: {session.calls}")


if __name__ == "__main__":
    main()
