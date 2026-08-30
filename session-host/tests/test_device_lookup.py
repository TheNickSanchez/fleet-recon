from __future__ import annotations

import asyncio

from fleet_session_host import device_lookup


def test_vuln_phrasing_short_circuits_without_mcp_or_sdk(settings_factory):
    settings = settings_factory()
    result = asyncio.run(
        device_lookup.run_device_lookup("jdoe", "any known vulnerabilities on jdoe's box?", settings)
    )
    assert result.status == "failed"
    assert "Tenable" in result.diagnostic
    assert result.card is None


def test_missing_mcp_config_returns_clear_diagnostic(settings_factory):
    settings = settings_factory()  # mcp_servers_config points at a nonexistent file
    result = asyncio.run(device_lookup.run_device_lookup("C02FL1234ABC", "look up C02FL1234ABC", settings))
    assert result.status == "failed"
    assert "MCP_SERVERS_CONFIG" in result.diagnostic
    assert result.card is None


def test_placeholder_mcp_config_returns_clear_diagnostic(settings_factory, tmp_path):
    settings = settings_factory()
    settings.mcp_servers_config.write_text(
        """
        {
          "mcpServers": {
            "jamf": {"transport": "stdio", "command": "<OPERATOR_SUPPLY: stdio command>", "args": []},
            "intune": {"transport": "stdio", "command": "<OPERATOR_SUPPLY: stdio command>", "args": []},
            "servicenow": {"transport": "stdio", "command": "<OPERATOR_SUPPLY: stdio command>", "args": []}
          }
        }
        """
    )
    result = asyncio.run(device_lookup.run_device_lookup("jdoe", "look up jdoe", settings))
    assert result.status == "failed"
    assert "OPERATOR_SUPPLY" in result.diagnostic


def test_allowed_tools_matches_device_lookup_skill():
    # MCP tools are always registered by the Claude Code CLI as
    # mcp__<server>__<tool>; the bare tool name is never callable.
    assert set(device_lookup.ALLOWED_TOOLS) == {
        "mcp__jamf__jamf_get_device_summary",
        "mcp__intune__intune_lookup_device",
        "mcp__servicenow__snow_lookup_user_profile",
    }
