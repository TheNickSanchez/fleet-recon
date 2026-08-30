from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from fleet_session_host import asset_ops


def _fake_run_factory(captured_argvs: list[list[str]], *, step2_returncode: int = 0):
    def fake_run(argv, cwd, capture_output, text, timeout, check):
        captured_argvs.append(list(argv))
        joined = " ".join(str(a) for a in argv)

        if "asset_report_build.py" in joined:
            out_path = Path(argv[argv.index("--output") + 1])
            out_path.write_text(
                "Username,Serial,Platform,State,Substate,Model,Asset Tag,Notes\n"
                "nina.patel,ABC123,macOS,In use,Primary,MacBook,AT1,\n"
                "chris.okonkwo,DEF456,Windows,In use,Primary,Latitude,AT2,\n"
            )
            return SimpleNamespace(returncode=0, stdout="[+] built 2 rows", stderr="")

        if "asset_report_mdm.py" in joined:
            loc_path = Path(argv[argv.index("--location") + 1])
            if step2_returncode != 0:
                return SimpleNamespace(returncode=step2_returncode, stdout="", stderr="jamf token error")
            df = pd.read_csv(loc_path, dtype=str).fillna("")
            df["MDM"] = ["Jamf", "Intune"]
            df["MDM Status"] = ["Managed", "Managed"]
            df["MDM Last Check-In"] = ["2026-08-20", "2026-08-21"]
            df["MDM Detail"] = ["", ""]
            df.to_csv(loc_path, index=False)
            return SimpleNamespace(returncode=0, stdout="[+] mdm added", stderr="")

        raise AssertionError(f"unexpected argv: {argv}")

    return fake_run


def test_fixed_argv_and_no_identity_leak(settings_factory, monkeypatch):
    settings = settings_factory()
    monkeypatch.setattr(asset_ops.shutil, "which", lambda name: "/usr/bin/passkey")

    captured: list[list[str]] = []
    monkeypatch.setattr(asset_ops.subprocess, "run", _fake_run_factory(captured))

    result = asset_ops.run_asset_ops(
        "run-1", settings, identities=["nina.patel", "chris.okonkwo"], csv_bytes=None
    )

    assert result.status == "completed"
    assert result.csv_preview["row_count"] == 2
    assert result.csv_preview["type"] == "chat.csv_preview"

    assert len(captured) == 2
    step1_argv, step2_argv = captured
    assert step1_argv[:4] == ["passkey", "run", "servicenow", "--"]
    assert "--platforms" in step1_argv and "macOS,Windows" in step1_argv
    assert step2_argv[:8] == ["passkey", "run", "jamf_api", "--", "passkey", "run", "intune", "--"]

    # The identity list must never appear on the command line -- only inside
    # the temp CSV file the host wrote.
    for argv in captured:
        for arg in argv:
            assert "nina.patel" not in str(arg)
            assert "chris.okonkwo" not in str(arg)

    # And the model-facing summaries never carry the CSV body or identities.
    assert "nina.patel" not in result.step1_summary
    assert "chris.okonkwo" not in result.step1_summary


def test_missing_passkey_returns_diagnostic_and_never_shells_out(settings_factory, monkeypatch):
    settings = settings_factory()
    monkeypatch.setattr(asset_ops.shutil, "which", lambda name: None)

    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess.run must not be called when passkey is missing")

    monkeypatch.setattr(asset_ops.subprocess, "run", fail_if_called)

    result = asset_ops.run_asset_ops("run-2", settings, identities=["jdoe"], csv_bytes=None)

    assert called is False
    assert result.status == "failed"
    assert "passkey" in result.diagnostic
    assert "servicenow" in result.diagnostic


def test_step2_failure_still_returns_partial_with_step1_rows(settings_factory, monkeypatch):
    settings = settings_factory()
    monkeypatch.setattr(asset_ops.shutil, "which", lambda name: "/usr/bin/passkey")
    captured: list[list[str]] = []
    monkeypatch.setattr(
        asset_ops.subprocess, "run", _fake_run_factory(captured, step2_returncode=1)
    )

    result = asset_ops.run_asset_ops(
        "run-3", settings, identities=["nina.patel", "chris.okonkwo"], csv_bytes=None
    )

    assert result.status == "partial"
    assert result.csv_preview is not None
    assert result.csv_preview["row_count"] == 2
    assert result.diagnostic is not None


def test_csv_upload_is_passed_through_and_input_count_dedupes(settings_factory, monkeypatch):
    settings = settings_factory()
    monkeypatch.setattr(asset_ops.shutil, "which", lambda name: "/usr/bin/passkey")
    captured: list[list[str]] = []
    monkeypatch.setattr(asset_ops.subprocess, "run", _fake_run_factory(captured))

    csv_bytes = b"Email\nnina.patel@example.com\nnina.patel@example.com\nchris.okonkwo@example.com\n"
    assert asset_ops.count_csv_identities(csv_bytes) == 2

    result = asset_ops.run_asset_ops("run-4", settings, identities=[], csv_bytes=csv_bytes)
    assert result.status == "completed"

    input_csv = settings.session_tmp_dir / "run-4-upload.csv"
    assert input_csv.read_bytes() == csv_bytes


def test_scripts_missing_returns_diagnostic(settings_factory, monkeypatch):
    settings = settings_factory(with_scripts=False)
    monkeypatch.setattr(asset_ops.shutil, "which", lambda name: "/usr/bin/passkey")

    result = asset_ops.run_asset_ops("run-5", settings, identities=["jdoe"], csv_bytes=None)

    assert result.status == "failed"
    assert "ASSET_OPS_SCRIPTS_DIR" in result.diagnostic
