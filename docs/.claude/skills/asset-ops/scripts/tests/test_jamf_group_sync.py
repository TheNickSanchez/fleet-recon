"""Offline tests for jamf_group_sync.py's asset_report.csv-based serial
extraction/dedupe — the pure logic that replaced the old joined-column
(Serial Number(s)/Platforms) parsing against servicenow_hardware_report.csv.

    .venv/bin/python scripts/tests/test_jamf_group_sync.py

No credentials, no network. jamf_group_sync.py checks for JAMF_* env vars at
import time and calls sys.exit(1) if they're missing (same pattern
intune_app_lookup.py uses), so dummy creds are set before the import below.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

os.environ.setdefault("JAMF_BASE_URL", "https://fake.jamfcloud.com")
os.environ.setdefault("JAMF_CLIENT_ID", "fake-client-id")
os.environ.setdefault("JAMF_CLIENT_SECRET", "fake-client-secret")

import pandas as pd  # noqa: E402

from fleet_common import BASE_COLUMNS  # noqa: E402
from jamf_group_sync import extract_macos_serials  # noqa: E402


def frame(rows):
    return pd.DataFrame(
        [{**dict.fromkeys(BASE_COLUMNS, ""), **r} for r in rows], columns=BASE_COLUMNS
    )


def test_filters_to_macos_only():
    df = frame([
        {"Username": "user.a", "Serial": "MAC001", "Platform": "macOS"},
        {"Username": "user.b", "Serial": "WIN001", "Platform": "Windows"},
        {"Username": "user.c", "Serial": "IPAD01", "Platform": "iOS/iPadOS"},
    ])
    assert extract_macos_serials(df) == {"MAC001"}
    print("  extract_macos_serials: only Platform == 'macOS' rows are kept")


def test_dedupes_by_serial_no_join_needed():
    """asset_report.csv is already one row per device, so a serial shared by two
    users (reassigned/shared asset) just collapses to one set entry -- no
    ';'-joined Serial Number(s) string to split the way the old
    servicenow_hardware_report.csv shape required."""
    df = frame([
        {"Username": "user.a", "Serial": "known1", "Platform": "macOS"},
        {"Username": "user.b", "Serial": "KNOWN1", "Platform": "macOS"},
        {"Username": "user.c", "Serial": "known2", "Platform": "macOS"},
    ])
    serials = extract_macos_serials(df)
    assert serials == {"KNOWN1", "KNOWN2"}, serials
    print("  extract_macos_serials: shared serial across two rows dedupes to one, uppercased")


def test_placeholder_and_blank_serials_excluded():
    """Placeholder serials (ServiceNow free-text data-entry values) and blank
    serials must never reach the Jamf inventory-validation call."""
    df = frame([
        {"Username": "user.a", "Serial": "PENDING", "Platform": "macOS"},
        {"Username": "user.b", "Serial": "", "Platform": "macOS"},
        {"Username": "user.c", "Serial": "N/A", "Platform": "macOS"},
        {"Username": "user.d", "Serial": "REALSERIAL1", "Platform": "macOS"},
    ])
    assert extract_macos_serials(df) == {"REALSERIAL1"}
    print("  extract_macos_serials: placeholder and blank serials are dropped")


def test_no_macos_devices_yields_empty_set():
    df = frame([
        {"Username": "user.a", "Serial": "WIN001", "Platform": "Windows"},
        {"Username": "user.b", "Serial": "", "Platform": "No Device Assigned"},
    ])
    assert extract_macos_serials(df) == set()
    print("  extract_macos_serials: no macOS rows -> empty set, not an error")


def test_mixed_case_platform_value_is_not_matched():
    """Platform is an exact match against the derive_platform() canonical value
    ('macOS'), not a case-insensitive substring -- asset_report_build.py always
    writes the canonical form, so a lowercase 'macos' would only appear on a
    malformed/hand-edited CSV and should not silently match."""
    df = frame([{"Username": "user.a", "Serial": "MAC001", "Platform": "macos"}])
    assert extract_macos_serials(df) == set()
    print("  extract_macos_serials: exact-cased 'macOS' required, no fuzzy platform match")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nall jamf_group_sync assertions passed")
