"""Offline tests for asset_report_html.py's bare-mode detection and render path.

    .venv/bin/python scripts/tests/test_asset_report_html_bare_mode.py

No credentials, no network, no live template rendering assumptions beyond the
placeholder-substitution contract build()/build_bare() both enforce: every
{{PLACEHOLDER}} in report/templates/asset-ops.html must be filled, or the
function exits with an error (checked here via subprocess-free direct calls,
so a failure surfaces as an AssertionError/SystemExit in this process).
"""

import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import asset_coverage as cov  # noqa: E402
from fleet_common import BASE_COLUMNS  # noqa: E402
import asset_report_html as h  # noqa: E402


def base_frame(rows):
    """Step-1-only shape: just the columns asset_report_build.py writes."""
    return pd.DataFrame(
        [{**dict.fromkeys(BASE_COLUMNS, ""), **r} for r in rows], columns=BASE_COLUMNS
    )


def test_bare_mode_detected_when_only_step_1_ran():
    df = base_frame([
        {"Username": "user.a", "Serial": "MAC001", "Platform": "macOS"},
        {"Username": "user.b", "Serial": "WIN001", "Platform": "Windows"},
    ])
    assert h.is_bare_mode(df) is True
    print("  is_bare_mode: true when no MDM Status and no '<App> Status' column exists")


def test_not_bare_once_mdm_status_present():
    df = base_frame([{"Username": "user.a", "Serial": "MAC001", "Platform": "macOS"}])
    df["MDM"] = "Jamf"
    df["MDM Status"] = "Managed"
    assert h.is_bare_mode(df) is False
    print("  is_bare_mode: false the moment step 2 (MDM Status) has run")


def test_not_bare_once_app_status_present():
    df = base_frame([{"Username": "user.a", "Serial": "MAC001", "Platform": "macOS"}])
    df["Zscaler Status"] = "OK - installed"
    df["Zscaler Health"] = "healthy"
    df["Zscaler Source"] = "ea:Compliance - Zscaler Status"
    assert h.is_bare_mode(df) is False
    print("  is_bare_mode: false the moment step 3 (an '<App> Status'/'<App> Health' pair) has run")


def test_app_status_column_alone_without_health_does_not_flip_mode():
    """app_names() requires the matching '<App> Health' column too -- a stray
    '<App> Status'-suffixed column with no Health pair (e.g. hand-edited CSV)
    must not be mistaken for a completed step 3."""
    df = base_frame([{"Username": "user.a", "Serial": "MAC001", "Platform": "macOS"}])
    df["Zscaler Status"] = "OK - installed"
    assert h.is_bare_mode(df) is True
    print("  is_bare_mode: an orphan '<App> Status' column with no Health pair stays bare")


def test_bare_outlier_bucket_matches_device_audit_definition():
    """Outliers = No Device Assigned + Not Found in SN + Unknown, ported verbatim
    from the old device-list-ops device_audit_report.py categorize() bucket."""
    df = base_frame([
        {"Username": "user.a", "Serial": "MAC001", "Platform": "macOS"},
        {"Username": "user.b", "Serial": "WIN001", "Platform": "Windows"},
        {"Username": "user.c", "Serial": "", "Platform": "No Device Assigned"},
        {"Username": "user.d", "Serial": "", "Platform": "Not Found in SN"},
        {"Username": "user.e", "Serial": "ODD001", "Platform": "Unknown"},
        # iPad is a real, resolvable device category -- NOT an outlier, unlike the
        # three buckets above. device-list-ops never had this platform to worry about.
        {"Username": "user.f", "Serial": "IPAD01", "Platform": "iOS/iPadOS"},
    ])
    outliers = int(df["Platform"].isin(h.BARE_OUTLIER_PLATFORMS).sum())
    assert outliers == 3, outliers
    print("  BARE_OUTLIER_PLATFORMS: No Device Assigned + Not Found in SN + Unknown only")


def _render_bare(df):
    return h.build_bare(df, "test.csv", "/tmp/asset-ops-test-bare.html",
                        "2026-08-27 09:00", "2026-08-27 09:05")


def test_bare_render_has_no_leftover_placeholders_and_no_verdict_language():
    df = base_frame([
        {"Username": "user.a", "Serial": "MAC001", "Platform": "macOS"},
        {"Username": "user.b", "Serial": "WIN001", "Platform": "Windows"},
        {"Username": "user.c", "Serial": "", "Platform": "No Device Assigned"},
    ])
    page = _render_bare(df)
    assert "{{" not in page, "unfilled template placeholder leaked into bare-mode output"
    # No coverage-verdict framing -- this is the neutral/no-escalation mode.
    assert "Action Needed" not in page
    assert "Needs Recheck" not in page
    assert 'class="verdict"' not in page
    # No Users tab -- a single flat Devices tab instead.
    assert 'data-tab="users"' not in page
    assert '<section id="users">' not in page
    assert 'data-tab="devices"' in page
    assert 'data-tab="summary"' in page
    print("  build_bare: renders cleanly with no verdict language and no Users tab")


def test_bare_render_stat_tiles_and_breakdown_are_present():
    df = base_frame([
        {"Username": "user.a", "Serial": "MAC001", "Platform": "macOS"},
        {"Username": "user.b", "Serial": "WIN001", "Platform": "Windows"},
        {"Username": "user.c", "Serial": "", "Platform": "No Device Assigned"},
        {"Username": "user.d", "Serial": "", "Platform": "Not Found in SN"},
    ])
    page = _render_bare(df)
    assert "<span>Users</span>" in page
    assert "<span>macOS</span>" in page
    assert "<span>Windows</span>" in page
    assert "<span>Outliers</span>" in page
    assert "Platform breakdown" in page
    print("  build_bare: neutral stat tiles (Users/macOS/Windows/Outliers) and breakdown table render")


def test_render_flips_to_coverage_framed_once_enriched():
    """The same CSV, once an MDM Status column exists, must render the full
    Users + Devices coverage-verdict tabs instead of the bare path."""
    rows = [
        {"Username": "user.a", "Serial": "MAC001", "Platform": "macOS", "State": "In use",
         "Substate": "Primary", "Model": "MacBook Pro", "Asset Tag": "A1", "Notes": "",
         "MDM": "Jamf", "MDM Status": "Managed", "MDM Last Check-In": "2026-08-20", "MDM Detail": ""},
    ]
    df = pd.DataFrame(rows)
    assert h.is_bare_mode(df) is False

    apps = h.app_names(df)
    df2, stats = cov.add_compliance(df, apps, today=dt.date(2026, 8, 27))
    page = h.build(df2, apps, stats, "test.csv", "/tmp/asset-ops-test-full.html",
                   "2026-08-27 09:00", "2026-08-27 09:05", "test-users.csv")
    assert "{{" not in page, "unfilled template placeholder leaked into coverage-framed output"
    assert 'data-tab="users"' in page
    assert '<section id="users">' in page
    print("  build: the moment MDM Status exists, rendering flips to the Users+Devices coverage view")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nall asset_report_html bare-mode assertions passed")
