from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from fleet_session_host import chat


def test_missing_litellm_settings_returns_clear_diagnostic(settings_factory):
    settings = settings_factory()
    result = asyncio.run(chat.run_chat_turn("run-1", "look up jdoe", settings))
    assert result.status == "failed"
    assert "LITELLM_MODEL" in result.diagnostic


def test_missing_claude_config_returns_clear_diagnostic(settings_factory):
    settings = replace(
        settings_factory(), anthropic_base_url="https://gateway.example", litellm_model="claude"
    )
    result = asyncio.run(chat.run_chat_turn("run-1", "look up jdoe", settings))
    assert result.status == "failed"
    assert "Claude Code config" in result.diagnostic


def test_load_mcp_servers_mirrors_operator_config(tmp_path):
    config_path = tmp_path / "claude.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "jamf": {"command": "jamf-mcp", "args": ["--flag"]},
                    "broken": {"args": []},  # no command -- must be skipped, not fabricated
                }
            }
        )
    )
    servers, error = chat._load_mcp_servers(config_path)
    assert error is None
    assert set(servers.keys()) == {"jamf"}
    assert servers["jamf"]["command"] == "jamf-mcp"
    assert servers["jamf"]["type"] == "stdio"


def test_load_mcp_servers_missing_file_is_a_diagnostic(tmp_path):
    servers, error = chat._load_mcp_servers(tmp_path / "nope.json")
    assert servers == {}
    assert "CLAUDE_CONFIG_PATH" in error


def test_load_mcp_servers_empty_servers_is_a_diagnostic(tmp_path):
    config_path = tmp_path / "claude.json"
    config_path.write_text(json.dumps({"mcpServers": {}}))
    servers, error = chat._load_mcp_servers(config_path)
    assert servers == {}
    assert "no usable mcpServers" in error


def test_render_history_empty_returns_prompt_unchanged():
    assert chat._render_history([], "hi") == "hi"


def test_render_history_stuffs_prior_turns_into_prompt():
    history = [("user", "my name is Nick"), ("assistant", "Got it, Nick.")]
    rendered = chat._render_history(history, "what's my name?")
    assert "my name is Nick" in rendered
    assert "Got it, Nick." in rendered
    assert rendered.endswith("New message from the user: what's my name?")


def test_disallowed_tools_keeps_raw_shell_and_filesystem_off() -> None:
    # See chat.py's module docstring: this repo's own two skills are already
    # implemented safely without Bash/Read/Write, so a shared, unauthenticated
    # host never gets raw shell access via the general chat session.
    assert "Bash" in chat.DISALLOWED_TOOLS
    assert "Write" in chat.DISALLOWED_TOOLS
    assert "Read" in chat.DISALLOWED_TOOLS


def test_friendly_tool_name_unwraps_mcp_namespacing():
    assert chat._friendly_tool_name("mcp__jamf__get_computer_by_username") == "jamf -> get_computer_by_username"


def test_friendly_tool_name_leaves_non_mcp_names_alone():
    assert chat._friendly_tool_name("build_asset_report") == "build_asset_report"


class _FakeToolUseBlock:
    def __init__(self, name: str) -> None:
        self.name = name


def test_describe_tool_use_calls_out_asset_report_by_name():
    line = chat._describe_tool_use(_FakeToolUseBlock("mcp__fleet_recon__build_asset_report"))
    assert line == "Building the asset report..."


def test_describe_tool_use_names_other_tools():
    line = chat._describe_tool_use(_FakeToolUseBlock("mcp__jamf__get_computer_by_username"))
    assert line == "Calling jamf -> get_computer_by_username..."


class _FakeToolResultBlock:
    def __init__(self, is_error: bool) -> None:
        self.is_error = is_error


def test_describe_tool_result_flags_errors():
    assert "failed" in chat._describe_tool_result(_FakeToolResultBlock(True))


def test_describe_tool_result_reports_success():
    assert chat._describe_tool_result(_FakeToolResultBlock(False)) == "Got a result back."
