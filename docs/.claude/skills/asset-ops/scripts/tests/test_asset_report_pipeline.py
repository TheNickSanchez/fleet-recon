"""Offline pipeline checks — duplicate serials, idempotency, no-silent-blanks.

    .venv/bin/python scripts/tests/test_asset_report_pipeline.py

Uses a fake Jamf session, so no credentials and no network. The duplicate-serial
case is the one that matters: a shared or reassigned asset appears on two rows,
and a serial-keyed result dict would drop one of them.
"""

import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from fleet_common import (  # noqa: E402
    BASE_COLUMNS, load_report, lookup_rows, set_columns, skip_reason, write_report,
)
import asset_report_app as app  # noqa: E402
import asset_report_mdm as mdm  # noqa: E402


class FakeJamf:
    """Returns one managed record for KNOWN1, nothing for GHOST1."""

    base = "https://fake.jamfcloud.com"
    calls = {"token": 1, "inventory": 0, "detail": 0}

    def inventory_batch(self, serials, sections):
        out = {}
        for serial in serials:
            if serial != "KNOWN1":
                continue
            out[serial] = {
                "id": "101",
                "hardware": {"serialNumber": serial},
                "general": {"name": "MAC-101", "lastContactTime": "2026-08-17T09:00:00Z",
                            "remoteManagement": {"managed": True}},
                "extensionAttributes": [
                    {"name": "Compliance - Zscaler Status", "values": ["OK - installed (4.8.0.83)"]}
                ],
            }
        self.calls["inventory"] += 1
        return out


def sample_frame():
    rows = [
        # Same serial on two users — shared/reassigned asset.
        {"Username": "user.a", "Serial": "KNOWN1", "Platform": "macOS", "State": "In use",
         "Substate": "Primary", "Model": "MacBook Pro", "Asset Tag": "A1", "Notes": ""},
        {"Username": "user.b", "Serial": "KNOWN1", "Platform": "macOS", "State": "In use",
         "Substate": "Secondary", "Model": "MacBook Pro", "Asset Tag": "A1", "Notes": ""},
        {"Username": "user.c", "Serial": "GHOST1", "Platform": "macOS", "State": "In stock",
         "Substate": "", "Model": "MacBook Air", "Asset Tag": "A2", "Notes": ""},
        {"Username": "user.d", "Serial": "", "Platform": "No Device Assigned", "State": "",
         "Substate": "", "Model": "", "Asset Tag": "", "Notes": "no hardware assigned"},
        {"Username": "user.e", "Serial": "ODD001", "Platform": "Unknown", "State": "In use",
         "Substate": "Primary", "Model": "Mystery Box", "Asset Tag": "A3", "Notes": ""},
        # Has a serial but no MDM record anywhere — must not read as "unknown".
        {"Username": "user.f", "Serial": "DSW017327V", "Platform": "Virtual Desktop",
         "State": "In use", "Substate": "Primary", "Model": "Parallels Virtual Desktop",
         "Asset Tag": "A4", "Notes": ""},
        # ServiceNow placeholder text in serial_number — must never reach an API.
        {"Username": "user.g", "Serial": "PENDING", "Platform": "macOS", "State": "In use",
         "Substate": "Primary", "Model": "MacBook Pro", "Asset Tag": "A5", "Notes": ""},
        # Apple-made but in Jamf's mobile inventory, not computers-inventory.
        {"Username": "user.h", "Serial": "DMPYFGKMJF8K", "Platform": "iOS/iPadOS",
         "State": "In use", "Substate": "Primary", "Model": "iPad 4 16GB WiFi",
         "Asset Tag": "A6", "Notes": ""},
    ]
    return pd.DataFrame(rows, columns=BASE_COLUMNS)


def fill_skipped(df, results, columns, blank):
    """Mirror the post-pass loop both step scripts run, via the shared reason helper."""
    for idx in df.index:
        if idx not in results:
            results[idx] = blank(skip_reason(str(df.at[idx, "Platform"]).strip(),
                                             df.at[idx, "Serial"]))
    return results


def test_duplicate_serial_gets_both_rows():
    df = sample_frame()
    rows, skipped = lookup_rows(df)
    # Only dispatchable rows come back: 3 macOS. The no-serial and Unknown-platform
    # rows are held out for the post-pass loop, which labels them explicitly.
    assert len(rows) == 3, rows
    assert skipped["Skipped (no serial)"] == 1
    assert skipped["Skipped (unknown platform)"] == 1
    assert skipped["Skipped (virtual desktop)"] == 1
    assert skipped["Skipped (placeholder serial)"] == 1, "PENDING would have hit the API"
    assert skipped["Skipped (mobile device)"] == 1
    assert "PENDING" not in {r["Serial"] for r in rows}

    macos = [r for r in rows if r["Platform"] == "macOS"]
    results = mdm.jamf_pass(FakeJamf(), macos, 40)
    assert set(results) == {0, 1, 2}, results
    assert results[0]["MDM Status"] == "Managed"
    assert results[1]["MDM Status"] == "Managed", "second row of a shared serial was dropped"
    assert results[2]["MDM Status"] == "Not Found in Jamf"
    print("  step 2: duplicate serial resolves both rows")


def test_app_duplicate_and_ea():
    df = sample_frame()
    rows, _ = lookup_rows(df)
    macos = [r for r in rows if r["Platform"] == "macOS"]
    cols = ["Zscaler Status", "Zscaler Health", "Zscaler Source"]
    results = app.jamf_pass(FakeJamf(), macos, "Zscaler", app.load_rules("Zscaler"), 40, cols)
    assert results[0]["Zscaler Status"] == "OK - installed (4.8.0.83)"
    assert results[1] == results[0], "second row of a shared serial diverged"
    assert results[0]["Zscaler Health"] == "healthy"
    assert results[0]["Zscaler Source"] == "ea:Compliance - Zscaler Status"
    assert results[2]["Zscaler Status"] == "Not Found in Jamf"
    print("  step 3: EA value + provenance land on every row of a shared serial")


def test_no_silent_blanks_and_idempotency():
    df = sample_frame()
    rows, _ = lookup_rows(df)
    macos = [r for r in rows if r["Platform"] == "macOS"]

    results = mdm.jamf_pass(FakeJamf(), macos, 40)
    results = fill_skipped(df, results, mdm.MDM_COLUMNS,
                           lambda r: {"MDM": r, "MDM Status": r,
                                      "MDM Last Check-In": "", "MDM Detail": ""})
    df = set_columns(df, results, mdm.MDM_COLUMNS)
    assert (df["MDM Status"].str.strip() != "").all(), "a row was left blank"
    assert df.at[3, "MDM Status"] == "Skipped (no serial)"
    assert df.at[4, "MDM Status"] == "Skipped (unknown platform)"
    assert df.at[5, "MDM Status"] == "Skipped (virtual desktop)"
    assert df.at[6, "MDM Status"] == "Skipped (placeholder serial)"
    assert df.at[7, "MDM Status"] == "Skipped (mobile device)"

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "asset_report.csv")
        write_report(df, path, backup=False)
        first = load_report(path)
        # Second identical pass must overwrite, not append.
        again = set_columns(first.copy(), results, mdm.MDM_COLUMNS)
        write_report(again, path)
        second = load_report(path)
        assert list(first.columns) == list(second.columns), "columns grew on re-run"
        assert first.equals(second), "values drifted on re-run"
        assert any(f.startswith("asset_report.bak-") for f in os.listdir(tmp)), "no backup written"
    print("  every row explained; re-run is idempotent and backed up")


if __name__ == "__main__":
    test_duplicate_serial_gets_both_rows()
    test_app_duplicate_and_ea()
    test_no_silent_blanks_and_idempotency()
    print("\nall pipeline assertions passed")
