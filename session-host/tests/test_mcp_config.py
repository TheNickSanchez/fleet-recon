from __future__ import annotations

from pathlib import Path

from fleet_session_host.mcp_config import load_mcp_config


def test_missing_file_is_not_configured(tmp_path: Path):
    status = load_mcp_config(tmp_path / "does-not-exist.json")
    assert status.configured is False
    assert "not found" in status.reason


def test_example_placeholders_are_detected(tmp_path: Path):
    example = Path(__file__).resolve().parents[1] / "config" / "mcp.stdio.example.json"
    payload = example.read_text(encoding="utf-8")
    config_path = tmp_path / "mcp.stdio.json"
    config_path.write_text(payload)

    status = load_mcp_config(config_path)
    assert status.configured is False
    assert "OPERATOR_SUPPLY" in status.reason


def test_filled_in_config_is_configured(tmp_path: Path):
    config_path = tmp_path / "mcp.stdio.json"
    config_path.write_text(
        """
        {
          "mcpServers": {
            "jamf": {"transport": "stdio", "command": "node", "args": ["jamf-mcp.js"]},
            "intune": {"transport": "stdio", "command": "node", "args": ["intune-mcp.js"]},
            "servicenow": {"transport": "stdio", "command": "node", "args": ["snow-mcp.js"]}
          }
        }
        """
    )
    status = load_mcp_config(config_path)
    assert status.configured is True
    assert set(status.servers.keys()) == {"jamf", "intune", "servicenow"}
