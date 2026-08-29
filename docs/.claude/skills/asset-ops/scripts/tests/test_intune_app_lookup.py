"""Offline tests for intune_app_lookup.py's asset_report.csv-based Windows-row
selection -- the pure logic that replaced reading Serial Number(s)/Platforms
columns off servicenow_hardware_report.csv.

    .venv/bin/python scripts/tests/test_intune_app_lookup.py

No credentials, no network. intune_app_lookup.py checks for INTUNE_* env vars
at import time and calls sys.exit(1) if they're missing, so dummy creds are
set before the import below.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

os.environ.setdefault("INTUNE_TENANT_ID", "fake-tenant")
os.environ.setdefault("INTUNE_CLIENT_ID", "fake-client-id")
os.environ.setdefault("INTUNE_CLIENT_SECRET", "fake-client-secret")

import pandas as pd  # noqa: E402

from fleet_common import BASE_COLUMNS  # noqa: E402
from intune_app_lookup import select_windows_rows  # noqa: E402


def frame(rows):
    return pd.DataFrame(
        [{**dict.fromkeys(BASE_COLUMNS, ""), **r} for r in rows], columns=BASE_COLUMNS
    )


def test_selects_windows_rows_only():
    df = frame([
        {"Username": "user.a", "Serial": "WIN001", "Platform": "Windows", "Model": "Latitude 5420"},
        {"Username": "user.b", "Serial": "MAC001", "Platform": "macOS", "Model": "MacBook Pro"},
        {"Username": "user.c", "Serial": "IPAD01", "Platform": "iOS/iPadOS", "Model": "iPad"},
    ])
    rows, skipped = select_windows_rows(df)
    assert rows == [{"Username": "user.a", "Serial": "WIN001", "Model": "Latitude 5420"}]
    assert skipped == {"macOS": 1, "iOS/iPadOS": 1}
    print("  select_windows_rows: only Platform == 'Windows' rows pass through, one row per device")


def test_no_serial_explosion_needed_unlike_old_shape():
    """asset_report.csv is already one row per device -- two Windows rows for two
    different users just both come through, with no ';'-joined Serial Number(s)/
    Platforms string to explode the way the old servicenow_hardware_report.csv
    shape required."""
    df = frame([
        {"Username": "user.a", "Serial": "WIN001", "Platform": "Windows", "Model": "Latitude"},
        {"Username": "user.b", "Serial": "WIN002", "Platform": "Windows", "Model": "Latitude"},
    ])
    rows, skipped = select_windows_rows(df)
    assert [r["Serial"] for r in rows] == ["WIN001", "WIN002"]
    assert skipped == {}
    print("  select_windows_rows: multiple Windows devices pass through with no explosion step")


def test_placeholder_serial_skipped_not_queried():
    df = frame([
        {"Username": "user.a", "Serial": "PENDING", "Platform": "Windows", "Model": "Latitude"},
        {"Username": "user.b", "Serial": "WIN002", "Platform": "Windows", "Model": "Latitude"},
    ])
    rows, skipped = select_windows_rows(df)
    assert [r["Serial"] for r in rows] == ["WIN002"]
    assert skipped == {"Skipped (placeholder serial)": 1}
    print("  select_windows_rows: placeholder serial never reaches an Intune lookup")


def test_no_device_and_not_found_are_counted_as_skips():
    df = frame([
        {"Username": "user.a", "Serial": "", "Platform": "No Device Assigned"},
        {"Username": "user.b", "Serial": "", "Platform": "Not Found in SN"},
    ])
    rows, skipped = select_windows_rows(df)
    assert rows == []
    assert skipped == {"No Device Assigned": 1, "Not Found in SN": 1}
    print("  select_windows_rows: No Device Assigned / Not Found in SN counted, not silently dropped")


def test_serial_normalized_to_uppercase():
    df = frame([{"Username": "user.a", "Serial": "win001", "Platform": "Windows", "Model": "Latitude"}])
    rows, _ = select_windows_rows(df)
    assert rows[0]["Serial"] == "WIN001"
    print("  select_windows_rows: serial is upper-cased for a consistent Intune serialNumber filter")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nall intune_app_lookup assertions passed")
