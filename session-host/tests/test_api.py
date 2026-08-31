from __future__ import annotations

from pathlib import Path

from fleet_session_host.api import _build_prompt


def test_build_prompt_text_only():
    assert _build_prompt("look up jdoe", None) == "look up jdoe"


def test_build_prompt_appends_csv_note():
    prompt = _build_prompt("here's the list", Path("/tmp/x-upload.csv"))
    assert "here's the list" in prompt
    assert "/tmp/x-upload.csv" in prompt
    assert "build_asset_report" in prompt


def test_build_prompt_csv_only_no_text():
    prompt = _build_prompt("", Path("/tmp/x-upload.csv"))
    assert "/tmp/x-upload.csv" in prompt
    assert prompt.strip() == prompt  # no leading blank line when text is empty
