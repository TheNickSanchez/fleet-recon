"""Offline tests for device compliance and per-user coverage rollup.

    .venv/bin/python scripts/tests/test_asset_coverage.py

No credentials, no network. The cases that matter are the ones where a naive
rollup gives a dangerously wrong answer: a user whose only working machine has not
checked in for months, and a user whose "extra devices" are iPads.
"""

import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import asset_coverage as cov  # noqa: E402

TODAY = dt.date(2026, 8, 18)


def frame(rows):
    cols = ["Username", "Serial", "Platform", "State", "Substate", "Model", "Asset Tag",
            "Notes", "MDM", "MDM Status", "MDM Last Check-In", "MDM Detail",
            "Zscaler Status", "Zscaler Health", "Zscaler Source"]
    return pd.DataFrame([{**dict.fromkeys(cols, ""), **r} for r in rows], columns=cols)


def dev(user, serial, mdm="Managed", health="healthy", checkin="2026-08-17",
        platform="macOS", substate="Primary"):
    return {"Username": user, "Serial": serial, "Platform": platform,
            "MDM Status": mdm, "Zscaler Health": health, "MDM Last Check-In": checkin,
            "Zscaler Status": "OK - installed", "State": "In use", "Substate": substate}


def run(rows, **kw):
    df, stats = cov.add_compliance(frame(rows), ["Zscaler"], today=TODAY, **kw)
    by_user = df.drop_duplicates("Username").set_index("Username")
    return df, stats, by_user


def test_mdm_binary():
    assert cov.mdm_state("Managed") == cov.MDM_MANAGED
    for v in ("Unmanaged", "Not Found in Jamf", "Not Found in Intune"):
        assert cov.mdm_state(v) == cov.MDM_NOT_MANAGED, v
    for v in ("Skipped (no serial)", "Skipped (mobile device)", ""):
        assert cov.mdm_state(v) == cov.MDM_NA, v
    print("  mdm_state: collapses to managed / not managed / not applicable")


def test_device_verdict():
    # Unmanaged but installed is non-compliant: nothing can be enforced on it.
    assert cov.device_verdict({"MDM Status": "Unmanaged", "Zscaler Health": "healthy"},
                              ["Zscaler"]) == cov.NON_COMPLIANT
    assert cov.device_verdict({"MDM Status": "Managed", "Zscaler Health": "healthy"},
                              ["Zscaler"]) == cov.COMPLIANT
    assert cov.device_verdict({"MDM Status": "Managed", "Zscaler Health": "unhealthy"},
                              ["Zscaler"]) == cov.NON_COMPLIANT
    assert cov.device_verdict({"MDM Status": "Managed", "Zscaler Health": "unknown"},
                              ["Zscaler"]) == cov.UNKNOWN
    assert cov.device_verdict({"MDM Status": "Skipped (mobile device)"}, ["Zscaler"]) == cov.UNKNOWN
    # MDM-only run: managed is all we can assert.
    assert cov.device_verdict({"MDM Status": "Managed"}, []) == cov.COMPLIANT
    print("  device_verdict: managed AND installed, unmanaged never passes")


def test_covered_user_is_not_in_the_action_list():
    """The whole point: 1 of 3 working means covered, not a remediation target."""
    _, _, by_user = run([
        dev("multi", "GOOD1"),
        dev("multi", "BAD1", health="unhealthy"),
        dev("multi", "BAD2", mdm="Not Found in Jamf", health="unknown"),
        dev("solo", "BAD3", health="unhealthy"),
    ])
    assert by_user.loc["multi", "Status"] == cov.COVERED
    assert by_user.loc["multi", "Coverage Ratio"] == "1/3"
    assert by_user.loc["solo", "Status"] == cov.NOT_COVERED
    assert by_user.loc["solo", "Coverage Ratio"] == "0/1"
    print("  rollup: 1-of-3 reads 'OK (multi device)'; 0-of-1 reads 'Action Needed'")


def test_straggler_note_points_at_the_working_device():
    df, stats, _ = run([dev("u", "GOOD1"), dev("u", "BAD1", health="unhealthy")])
    bad = df[df.Serial == "BAD1"].iloc[0]
    assert bad["Coverage Note"] == "already has a working device: GOOD1", bad["Coverage Note"]
    # A compliant row is never annotated, and neither is an uncovered user's row.
    assert df[df.Serial == "GOOD1"].iloc[0]["Coverage Note"] == ""
    assert stats["stragglers"] == 1
    assert stats["action_devices"] == 0
    print("  straggler note: names the working serial, only on failing rows")


def test_stale_sole_compliant_device_is_not_coverage():
    """A device compliant on paper but unseen for two months is not a working setup."""
    _, _, by_user = run([
        dev("stale", "OLD1", checkin="2026-06-20"),                    # 59d
        dev("fresh", "NEW1", checkin="2026-08-10"),                    # 8d
        dev("mixed", "OLD2", checkin="2026-06-20"),
        dev("mixed", "NEW2", checkin="2026-08-16"),
    ])
    assert by_user.loc["stale", "Status"] == cov.COVERAGE_STALE
    assert by_user.loc["fresh", "Status"] == cov.FULLY_COMPLIANT
    # One fresh compliant device is enough; staleness only bites when ALL are stale.
    assert by_user.loc["mixed", "Status"] == cov.FULLY_COMPLIANT
    print("  staleness: sole stale compliant device demotes to 'Needs Recheck'")


def test_unmeasurable_devices_stay_out_of_the_denominator():
    """A Mac plus two iPads is 1/1, not 1/3 -- otherwise iPads invent a failure."""
    _, _, by_user = run([
        dev("u", "MAC1"),
        dev("u", "IPAD1", mdm="Skipped (mobile device)", platform="iOS/iPadOS"),
        dev("u", "VDI1", mdm="Skipped (virtual desktop)", platform="Virtual Desktop"),
    ])
    assert by_user.loc["u", "Coverage Ratio"] == "1/1"
    assert by_user.loc["u", "Status"] == cov.FULLY_COMPLIANT
    print("  denominator: only checkable devices count")


def test_no_device_and_unmeasurable_are_distinct():
    _, _, by_user = run([
        {"Username": "nodev", "Platform": "No Device Assigned", "MDM Status": "Skipped (no serial)"},
        dev("ipad_only", "IPAD9", mdm="Skipped (mobile device)", platform="iOS/iPadOS"),
    ])
    assert by_user.loc["nodev", "Status"] == cov.NO_DEVICE
    # Has hardware, but nothing we can check -- do not report as a compliance failure.
    assert by_user.loc["ipad_only", "Status"] == cov.UNMEASURABLE
    print("  buckets: 'No Device' and 'Can't Verify' stay separate from 'Action Needed'")


def test_return_states_flag():
    rows = [dev("u", "GOOD1"),
            dev("u", "RET1", health="unhealthy", substate="REPL - Waiting on Return")]
    _, _, keep = run(rows)
    assert keep.loc["u", "Coverage Ratio"] == "1/2"
    _, _, drop = run(rows, ignore_return_states=True)
    assert drop.loc["u", "Coverage Ratio"] == "1/1"
    assert drop.loc["u", "Status"] == cov.FULLY_COMPLIANT
    print("  --ignore-return-states: drops returning assets from the ratio only when asked")


def test_multi_app_requires_all():
    df = frame([dev("u", "S1")])
    df["Slack Status"], df["Slack Health"] = "Requires update", "unhealthy"
    both, _ = cov.add_compliance(df, ["Zscaler", "Slack"], today=TODAY)
    assert both.iloc[0]["Device Compliant"] == cov.NON_COMPLIANT
    one, _ = cov.add_compliance(df, ["Zscaler"], today=TODAY)
    assert one.iloc[0]["Device Compliant"] == cov.COMPLIANT
    print("  multi-app: all scored apps must pass; --compliance-app narrows it")


def test_user_rows_worst_first():
    df, _, _ = run([dev("ok", "G1"), dev("bad", "B1", health="unhealthy"),
                    dev("part", "G2"), dev("part", "B2", health="unhealthy")])
    rows = cov.user_rows(df)
    assert rows[0]["Status"] == cov.NOT_COVERED
    assert rows[0]["Username"] == "bad"
    assert rows[0]["Priority"] == 1
    assert [r["Username"] for r in rows][-1] == "ok"
    print("  user_rows: sorted worst status first, Priority mirrors the order")


def test_user_rows_values_are_atomic():
    """Export correctness depends on these never being pre-formatted strings."""
    df, _, _ = run([dev("u", "GOOD1"), dev("u", "BAD1", health="unhealthy"),
                    dev("u", "BAD2", mdm="Unmanaged")])
    r = cov.user_rows(df)[0]
    assert r["Needs Work"] == ["BAD1", "BAD2"], r["Needs Work"]
    assert r["Working"] == ["GOOD1"]
    assert r["Platforms"] == ["macOS"]
    assert isinstance(r["Compliant"], int) and isinstance(r["Devices"], int)
    assert r["Compliant"] == 1 and r["Devices"] == 3
    assert isinstance(r["Issues"], list) and all(isinstance(i, tuple) for i in r["Issues"])
    # Ratio stays available for display, but the counts are what exports carry.
    assert r["Ratio"] == "1/3"
    print("  user_rows: lists stay lists and counts stay ints, ready for CSV")


def test_stale_user_with_nothing_failing_still_states_the_problem():
    """A blank 'blocking issue' on an action-list row reads as 'nothing to do'."""
    df, _, _ = run([dev("stale", "OLD1", checkin="2026-06-20")])
    r = cov.user_rows(df)[0]
    assert r["Status"] == cov.COVERAGE_STALE
    assert r["Needs Work"] == [], "nothing is actually failing on this device"
    assert r["Stale Days"] == 59
    assert r["Issues"] == [("working device not seen for 59d", 1)], r["Issues"]
    print("  stale user: blocking issue names the staleness, never left blank")


def test_format_issues_ascii_for_csv():
    issues = [("Unmanaged", 2), ("not installed", 1)]
    assert cov.format_issues(issues) == "2× Unmanaged · 1× not installed"
    assert cov.format_issues(issues, sep="; ", times="x") == "2x Unmanaged; 1x not installed"
    assert cov.format_issues([]) == ""
    print("  format_issues: pretty for the page, ASCII for the spreadsheet")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nall coverage assertions passed")
