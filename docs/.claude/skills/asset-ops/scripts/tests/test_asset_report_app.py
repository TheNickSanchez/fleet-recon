"""Offline checks for step 3's pure logic — no API calls, no credentials.

    .venv/bin/python scripts/tests/test_asset_report_app.py

Covers the two traps that silently corrupt results: en-dash EA names and the
four shapes Jamf returns extension attributes in.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from fleet_common import extension_attributes, normalize_label  # noqa: E402
from asset_report_app import classify, load_rules, resolve_ea_name  # noqa: E402

LIVE_EA_NAMES = [
    "Compliance - Zscaler Status",
    "Compliance - Slack",
    "Compliance – Nessus – Connectivity",   # en-dash, as Jamf really returns it
    "Compliance - Nessus - Plugin",
    "Compliance - Cortex Status",
    "Compliance - Global Protect",
    "Claude Code Version",
]


def test_normalize_label():
    assert normalize_label("Compliance – Nessus") == normalize_label("compliance - nessus")
    assert normalize_label("  A   B  ") == "a b"
    assert normalize_label(None) == ""
    print("  normalize_label: dash/case/whitespace unified")


def test_ea_resolution():
    zs = load_rules("Zscaler")
    assert zs, "zscaler rule should load from app_signal_map.yaml"
    name, ambig = resolve_ea_name("Zscaler", LIVE_EA_NAMES, zs)
    assert name == "Compliance - Zscaler Status", name

    # No override entry: dynamic match must still find it.
    name, ambig = resolve_ea_name("Slack", LIVE_EA_NAMES, {})
    assert name == "Compliance - Slack", name
    assert ambig == [], ambig

    # Ambiguous token, one of them en-dashed. Override pins it; without the
    # override both are reported rather than silently picking one.
    name, ambig = resolve_ea_name("Nessus", LIVE_EA_NAMES, load_rules("nessus"))
    assert name == "Compliance - Nessus - Plugin", name
    name, ambig = resolve_ea_name("Nessus", LIVE_EA_NAMES, {})
    assert len(ambig) == 1, ambig

    # En-dashed override path must still match the en-dashed live name.
    name, _ = resolve_ea_name("nessus-conn", LIVE_EA_NAMES,
                              {"paths": ["extensionAttributes.Compliance - Nessus - Connectivity"]})
    assert name == "Compliance – Nessus – Connectivity", name

    # Unknown app → no EA, which routes to the inventory fallback.
    assert resolve_ea_name("Figma", LIVE_EA_NAMES, {})[0] is None
    print("  resolve_ea_name: override > dynamic > none, en-dash safe")


def test_classify():
    zs = load_rules("Zscaler")
    assert classify("OK - installed (4.8.0.83)", zs) == "healthy"
    # Windows reports a bare "installed" — must not fall through to unknown.
    assert classify("installed", zs) == "healthy"
    # Contains both "installed" and "error" — unhealthy must win.
    assert classify("ERROR - Installed (Not Enrolled)", zs) == "unhealthy"
    assert classify("ERROR - no logs (pkg never ran)", zs) == "unhealthy"
    assert classify("not installed", zs) == "unhealthy"
    assert classify("status = not enrolled; deferrals = 0/3", zs) == "unhealthy"
    assert classify("notApplicable", zs) == "unknown"
    assert classify("", zs) == "unknown"
    assert classify("Requires update", load_rules("Slack")) == "unhealthy"
    # Generic lists for an app with no override.
    assert classify("installed (2026.1)", {}) == "healthy"
    assert classify("not installed", {}) == "unhealthy"
    assert classify("notApplicable", {}) == "unknown"
    print("  classify: unhealthy precedence holds on mixed-signal strings")


def test_extension_attributes_shapes():
    value = ["OK - installed (4.8.0.83)"]
    shapes = [
        {"extensionAttributes": [{"name": "Compliance - Zscaler Status", "values": value}]},
        {"extension_attributes": [{"name": "Compliance - Zscaler Status", "values": value}]},
        {"general": {"extensionAttributes": [{"name": "Compliance - Zscaler Status", "value": value}]}},
        {"general": {"extension_attributes": {"Compliance - Zscaler Status": value}}},
    ]
    for n, payload in enumerate(shapes, 1):
        attrs = extension_attributes(payload)
        got = attrs.get("Compliance - Zscaler Status")
        assert got == "OK - installed (4.8.0.83)", f"shape {n}: {got!r}"

    # Multi-line EA payloads are real; newlines in a CSV cell break grep/awk and
    # the console summary, so they must collapse without losing a field.
    multi = extension_attributes({"extensionAttributes": [
        {"name": "Compliance - Zscaler Status",
         "values": ["status = not enrolled\ndeferrals = 1/3\nlast_action = deferred"]}
    ]})["Compliance - Zscaler Status"]
    assert "\n" not in multi, multi
    assert multi == "status = not enrolled; deferrals = 1/3; last_action = deferred", multi
    print("  extension_attributes: 4 payload shapes flatten; multi-line collapses to one line")


if __name__ == "__main__":
    test_normalize_label()
    test_ea_resolution()
    test_classify()
    test_extension_attributes_shapes()
    print("\nall step-3 assertions passed")
