from __future__ import annotations

from pathlib import Path

import pytest

from fleet_session_host.settings import Settings


@pytest.fixture
def settings_factory(tmp_path: Path):
    def _make(*, with_scripts: bool = True) -> Settings:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        if with_scripts:
            (scripts_dir / "asset_report_build.py").write_text("# stub\n")
            (scripts_dir / "asset_report_mdm.py").write_text("# stub\n")
        tmp_dir = tmp_path / "tmp"
        reports_dir = tmp_path / "reports"
        tmp_dir.mkdir(exist_ok=True)
        reports_dir.mkdir(exist_ok=True)
        return Settings(
            host="127.0.0.1",
            port=8100,
            asset_ops_scripts_dir=scripts_dir,
            session_tmp_dir=tmp_dir,
            session_reports_dir=reports_dir,
            mcp_transport="stdio",
            mcp_servers_config=tmp_path / "mcp.stdio.json",
            anthropic_base_url="",
            anthropic_api_key="",
            litellm_model="",
        )

    return _make
