"""Sync macOS devices from asset_report.csv into a Jamf static computer group.

    passkey run jamf_api -- .venv/bin/python scripts/jamf_group_sync.py \
      --group-id <GROUP_ID>

Reads the asset-ops pipeline's device-grained asset_report.csv (Serial/Platform
columns, one row per device already) rather than the old joined-column
servicenow_hardware_report.csv user_hardware_lookup.py used to produce. Because
asset_report.csv is already one row per device, there is no ';'-joined
Serial Number(s)/Platforms string to split — just filter rows to Platform ==
"macOS" and dedupe by Serial.
"""

import argparse
import json
import math
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
import pandas as pd
import requests

from fleet_common import DEFAULT_REPORT, is_real_serial

JAMF_URL = os.environ.get("JAMF_BASE_URL", "").rstrip("/")
JAMF_CLIENT_ID = os.environ.get("JAMF_CLIENT_ID", "")
JAMF_CLIENT_SECRET = os.environ.get("JAMF_CLIENT_SECRET", "")

if not all([JAMF_URL, JAMF_CLIENT_ID, JAMF_CLIENT_SECRET]):
    print("[-] Missing credentials. Run via: passkey run jamf_api -- .venv/bin/python scripts/jamf_group_sync.py --location <file> --group-id <id>")
    sys.exit(1)

# Serials per Classic API PUT. Jamf handles ~100+ reliably in this tenant.
CHUNK_SIZE = 120


def get_jamf_token(http: requests.Session | None = None) -> tuple[str | None, float]:
    """Fetch a bearer token via OAuth client credentials."""
    try:
        client = http or requests
        resp = client.post(
            f"{JAMF_URL}/api/oauth/token",
            data={
                "client_id": JAMF_CLIENT_ID,
                "client_secret": JAMF_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        )
        if resp.status_code == 200:
            body = resp.json()
            token = body.get("access_token")
            expires_in = int(body.get("expires_in", 1800))
            # Refresh slightly early to avoid mid-request expiry.
            refresh_at = time.time() + max(60, expires_in - 120)
            return token, refresh_at
        else:
            print(f"[-] Failed to get Jamf token ({resp.status_code}): {resp.text}")
            return None, 0.0
    except Exception as e:
        print(f"[-] Token connection error: {e}")
        return None, 0.0


class JamfSession:
    """Small helper for token reuse and request counting."""

    def __init__(self):
        self.http = requests.Session()
        self.token: str | None = None
        self.refresh_at = 0.0
        self.calls = {
            "token": 0,
            "inventory": 0,
            "group_get": 0,
            "group_put": 0,
            "computer_get": 0,
        }

    def auth_header(self) -> dict[str, str]:
        if not self.token or time.time() >= self.refresh_at:
            self.refresh_token()
        if not self.token:
            raise RuntimeError("Jamf token unavailable")
        return {"Authorization": f"Bearer {self.token}"}

    def refresh_token(self) -> None:
        self.calls["token"] += 1
        token, refresh_at = get_jamf_token(self.http)
        self.token = token
        self.refresh_at = refresh_at


def serial_for_jamf_id(jamf_id: str, session: JamfSession) -> str | None:
    """Look up serial number for a Jamf computer ID via Classic API."""
    try:
        headers = session.auth_header() | {"Accept": "application/xml"}
        session.calls["computer_get"] += 1
        r = session.http.get(
            f"{JAMF_URL}/JSSResource/computers/id/{jamf_id}",
            headers=headers,
        )
        if r.status_code == 200:
            root = ET.fromstring(r.text)
            el = root.find(".//serial_number")
            return el.text.strip().upper() if el is not None and el.text else None
    except Exception:
        pass
    return None


def put_serials(serials: list[str], group_id: str, session: JamfSession) -> requests.Response:
    """PUT a full replacement member list to a Classic API static group."""
    computers_xml = "".join(
        f"<computer><serial_number>{s}</serial_number></computer>" for s in serials
    )
    body = f"<computer_group><computers>{computers_xml}</computers></computer_group>"
    headers = session.auth_header() | {
        "Content-Type": "text/xml",
        "Accept": "text/xml",
    }
    session.calls["group_put"] += 1
    return session.http.put(
        f"{JAMF_URL}/JSSResource/computergroups/id/{group_id}",
        headers=headers,
        data=body.encode(),
    )


def get_group_serials(group_id: str, session: JamfSession) -> set[str]:
    """Return current serials already in the target static group."""
    resp = None
    max_attempts = 8
    for attempt in range(max_attempts):
        headers = session.auth_header() | {"Accept": "application/xml"}
        session.calls["group_get"] += 1
        resp = session.http.get(
            f"{JAMF_URL}/JSSResource/computergroups/id/{group_id}",
            headers=headers,
        )
        if resp.status_code == 200:
            break
        if resp.status_code in (401, 404):
            # Jamf Classic can occasionally return transient 404/401 due to edge auth state.
            session.refresh_token()
            time.sleep(min(2.0, 0.25 * (attempt + 1)))
            continue
        resp.raise_for_status()

    if resp is None:
        raise RuntimeError("Group lookup request failed unexpectedly")
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    serials: set[str] = set()
    for el in root.findall(".//serial_number"):
        if el.text:
            serials.add(el.text.strip().upper())
    return serials


def push_chunked(enrolled_serials: set[str], group_id: str, session: JamfSession) -> tuple[int, set[str]]:
    """
    Push serials to a Jamf static group using accumulating chunked PUTs.

    Strategy: each PUT sends all previously-accepted serials PLUS the next chunk.
    This avoids Jamf's 409 unmanaged error from corrupting the full set.
    On a 409, resolve the bad Jamf IDs to serials, drop them, and retry the chunk.

    Returns (added_count, unmanaged_serials).
    """
    serial_list = sorted(enrolled_serials)
    total = len(serial_list)
    committed: list[str] = []
    unmanaged_serials: set[str] = set()
    chunk_num = 0

    for i in range(0, total, CHUNK_SIZE):
        chunk = serial_list[i : i + CHUNK_SIZE]
        chunk_num += 1
        total_chunks = math.ceil(total / CHUNK_SIZE)

        # Retry this chunk to handle unmanaged-device retries and token refreshes.
        for attempt in range(4):
            to_send = committed + chunk
            print(f"[*] Chunk {chunk_num}/{total_chunks}: pushing {len(to_send)} devices (attempt {attempt + 1})...")
            response = put_serials(to_send, group_id, session)

            if response.status_code in (200, 201):
                committed = to_send
                break

            if response.status_code == 401:
                print("    [!] Jamf token expired during push — refreshing token and retrying chunk...")
                session.refresh_token()
                if not session.token:
                    print("[-] Failed to refresh Jamf token during chunk push.")
                    return len(committed), unmanaged_serials
                continue

            if response.status_code == 409 and "unmanaged" in response.text:
                ids_match = re.search(r'IDs are unmanaged[^:]*:\s*([\d,\s]+)', response.text)
                if ids_match:
                    unmanaged_ids = [x.strip() for x in ids_match.group(1).split(",") if x.strip()]
                    print(f"    [!] {len(unmanaged_ids)} unmanaged Jamf IDs — resolving serials...")
                    for jamf_id in unmanaged_ids:
                        serial = serial_for_jamf_id(jamf_id, session)
                        if serial:
                            unmanaged_serials.add(serial)
                            if serial in chunk:
                                chunk.remove(serial)
                    continue  # retry with cleaned chunk

            # Non-retryable error
            print(f"[-] Jamf API Error ({response.status_code}): {response.text[:300]}")
            return len(committed), unmanaged_serials

        # Small sleep between chunks to reduce lock contention
        if i + CHUNK_SIZE < total:
            time.sleep(0.3)

    return len(committed), unmanaged_serials


def extract_macos_serials(df: pd.DataFrame) -> set[str]:
    """macOS serials from asset_report.csv, deduped by Serial.

    asset_report.csv (scripts/asset_report_build.py) is already one row per
    device, so this is a straight Platform filter plus a placeholder-serial
    guard -- no ';'-joined Serial Number(s)/Platforms string to split the way
    the old servicenow_hardware_report.csv-based sync required.
    """
    return {
        str(row["Serial"]).strip().upper()
        for _, row in df.iterrows()
        if str(row["Platform"]).strip() == "macOS" and is_real_serial(row["Serial"])
    }


def write_summary(summary_json: str | None, summary: dict) -> None:
    if not summary_json:
        return
    with open(summary_json, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, separators=(",", ":")) + "\n")


def sync_macs_to_jamf(
    file_location: str,
    group_id: str,
    dry_run: bool = False,
    mode: str = "additive",
    summary_json: str | None = None,
):
    run_start = time.time()
    phase_ms = {
        "csv_parse": 0.0,
        "inventory_validate": 0.0,
        "group_read": 0.0,
        "push": 0.0,
    }
    print(f"[*] Parsing asset report from: {file_location}")

    # 1. Load the device-grained asset report (one row per device already).
    parse_start = time.time()
    try:
        df = pd.read_csv(file_location, dtype=str).fillna("")
    except Exception as e:
        print(f"[-] Error reading file: {e}")
        return

    missing = [c for c in ("Serial", "Platform") if c not in df.columns]
    if missing:
        print(f"[-] {file_location} is missing required column(s): {', '.join(missing)}")
        print("    This script reads the asset-ops pipeline's asset_report.csv "
              "(scripts/asset_report_build.py), not a hardware-report CSV.")
        return

    serial_numbers = extract_macos_serials(df)

    if not serial_numbers:
        print("[-] No macOS devices found in the provided CSV report.")
        return

    phase_ms["csv_parse"] = (time.time() - parse_start) * 1000

    print(f"[+] Found {len(serial_numbers)} unique macOS serial numbers to sync.")

    # 4. Create Jamf session and fetch token.
    session = JamfSession()
    session.refresh_token()
    if not session.token:
        print("[-] Aborting sync due to missing authentication token.")
        return

    # 5. Validate serials against Jamf inventory (40 at a time via RSQL)
    inv_start = time.time()
    enrolled_serials: set[str] = set()
    unmanaged_preflight: set[str] = set()
    serial_list = sorted(serial_numbers)
    total_inv_batches = math.ceil(len(serial_list) / 40)
    for i in range(0, len(serial_list), 40):
        batch = serial_list[i : i + 40]
        batch_num = i // 40 + 1
        print(f"[*] Inventory validation batch {batch_num}/{total_inv_batches}...")
        filter_str = ",".join(f'hardware.serialNumber=="{s}"' for s in batch)
        try:
            resp = session.http.get(
                f"{JAMF_URL}/api/v1/computers-inventory",
                headers=session.auth_header(),
                params={"filter": filter_str, "section": "GENERAL,HARDWARE", "page-size": 100},
            )
            session.calls["inventory"] += 1
            resp.raise_for_status()
            for computer in resp.json().get("results", []):
                serial = (computer.get("hardware", {}).get("serialNumber") or "").upper()
                if serial:
                    remote_mgmt = (computer.get("general", {}).get("remoteManagement") or {})
                    # Pre-skip unmanaged endpoints to avoid expensive Classic API 409 retries.
                    if remote_mgmt.get("managed") is False:
                        unmanaged_preflight.add(serial)
                    else:
                        enrolled_serials.add(serial)
        except Exception as e:
            print(f"[-] Inventory validation failed (batch {batch_num}): {e}")
            return
    phase_ms["inventory_validate"] = (time.time() - inv_start) * 1000

    not_enrolled = serial_numbers - enrolled_serials - unmanaged_preflight
    if not_enrolled:
        print(f"[!] {len(not_enrolled)} serials not found in Jamf (skipping): {', '.join(sorted(not_enrolled))}")
    if unmanaged_preflight:
        print(f"[!] {len(unmanaged_preflight)} serials found but unmanaged in Jamf (preflight skip): {', '.join(sorted(unmanaged_preflight))}")
    print(f"[+] {len(enrolled_serials)} serials confirmed enrolled in Jamf.")

    if not enrolled_serials:
        print("[-] No enrolled devices to add. Aborting.")
        return

    # 6. Build target set based on sync mode.
    grp_start = time.time()
    existing_group_serials = get_group_serials(group_id, session)
    phase_ms["group_read"] = (time.time() - grp_start) * 1000
    if mode == "additive":
        serials_to_add = enrolled_serials - existing_group_serials
        target_serials = existing_group_serials | enrolled_serials
    else:
        serials_to_add = enrolled_serials
        target_serials = enrolled_serials

    print(
        f"[*] Preflight: mode={mode} existing={len(existing_group_serials)} "
        f"enrolled={len(enrolled_serials)} planned_add={len(serials_to_add)} "
        f"target={len(target_serials)}"
    )

    # 7. Dry-run: print what would be added and exit
    if dry_run:
        print(f"[~] DRY RUN — {len(serials_to_add)} devices would be added to Group {group_id}:")
        for s in sorted(serials_to_add):
            print(f"    {s}")
        duration = time.time() - run_start
        summary = {
            "group_id": group_id,
            "mode": mode,
            "dry_run": True,
            "no_op": False,
            "counts": {
                "serials_input": len(serial_numbers),
                "enrolled": len(enrolled_serials),
                "not_found": len(not_enrolled),
                "existing_group": len(existing_group_serials),
                "planned_add": len(serials_to_add),
                "target": len(target_serials),
                "added": 0,
                "unmanaged": len(unmanaged_preflight),
            },
            "calls": session.calls,
            "phase_ms": phase_ms,
            "duration_s": round(duration, 2),
        }
        write_summary(summary_json, summary)
        return

    if mode == "additive" and not serials_to_add:
        duration = time.time() - run_start
        print(f"[+] No-op: group already contains all {len(enrolled_serials)} enrolled devices.")
        print(
            f"[+] Summary: duration_s={duration:.2f} token_calls={session.calls['token']} "
            f"inventory_calls={session.calls['inventory']} group_get_calls={session.calls['group_get']} "
            f"group_put_calls={session.calls['group_put']} computer_get_calls={session.calls['computer_get']}"
        )
        summary = {
            "group_id": group_id,
            "mode": mode,
            "dry_run": False,
            "no_op": True,
            "counts": {
                "serials_input": len(serial_numbers),
                "enrolled": len(enrolled_serials),
                "not_found": len(not_enrolled),
                "existing_group": len(existing_group_serials),
                "planned_add": len(serials_to_add),
                "target": len(target_serials),
                "added": 0,
                "unmanaged": len(unmanaged_preflight),
            },
            "calls": session.calls,
            "phase_ms": phase_ms,
            "duration_s": round(duration, 2),
        }
        write_summary(summary_json, summary)
        return

    # 8. Push union set via chunked accumulating PUTs
    print(f"[*] Pushing target set of {len(target_serials)} devices to Jamf Static Group ID: {group_id}...")
    push_start = time.time()
    added, unmanaged_runtime = push_chunked(target_serials, group_id, session)
    phase_ms["push"] = (time.time() - push_start) * 1000
    unmanaged_total = unmanaged_preflight | unmanaged_runtime
    expected_added = len(target_serials) - len(unmanaged_runtime)
    duration = time.time() - run_start

    if added == expected_added:
        print(f"[+] Success! Added {added} macOS devices to Group {group_id}.")
    else:
        print(f"[-] Partial sync: added {added}/{expected_added} expected macOS devices to Group {group_id}.")
        sys.exit(1)
    if unmanaged_total:
        print(f"[!] {len(unmanaged_total)} unmanaged devices skipped: {', '.join(sorted(unmanaged_total))}")
    print(
        f"[+] Summary: duration_s={duration:.2f} token_calls={session.calls['token']} "
        f"inventory_calls={session.calls['inventory']} group_get_calls={session.calls['group_get']} "
        f"group_put_calls={session.calls['group_put']} computer_get_calls={session.calls['computer_get']} "
        f"not_found={len(not_enrolled)} unmanaged={len(unmanaged_total)}"
    )
    summary = {
        "group_id": group_id,
        "mode": mode,
        "dry_run": False,
        "no_op": False,
        "counts": {
            "serials_input": len(serial_numbers),
            "enrolled": len(enrolled_serials),
            "not_found": len(not_enrolled),
            "existing_group": len(existing_group_serials),
            "planned_add": len(serials_to_add),
            "target": len(target_serials),
            "added": added,
                "unmanaged": len(unmanaged_total),
        },
        "calls": session.calls,
        "phase_ms": phase_ms,
        "duration_s": round(duration, 2),
    }
    write_summary(summary_json, summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync macOS serial numbers from asset_report.csv into a target Jamf Static Computer Group."
    )
    parser.add_argument(
        "--location",
        default=DEFAULT_REPORT,
        help=f"Path to the asset report CSV (default: {DEFAULT_REPORT})."
    )
    parser.add_argument(
        "--group-id", "-g",
        required=True,
        help="The Jamf Pro target static computer group ID (e.g., 142)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print serials that would be added without pushing to Jamf."
    )
    parser.add_argument(
        "--mode",
        choices=["additive", "replace"],
        default="additive",
        help="Sync behavior: additive preserves existing members (default), replace overwrites group membership."
    )
    parser.add_argument(
        "--summary-json",
        help="Optional path to append one JSON summary object per run (jsonl format)."
    )
    args = parser.parse_args()

    sync_macs_to_jamf(
        args.location,
        args.group_id,
        dry_run=args.dry_run,
        mode=args.mode,
        summary_json=args.summary_json,
    )
