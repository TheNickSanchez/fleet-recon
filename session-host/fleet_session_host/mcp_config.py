"""Loads the operator-filled stdio MCP config (SAD §2.4, setup.md MCP section).

Only ``session-host/config/mcp.stdio.json`` (stdio transport) is read. HTTP
MCP is explicitly out of scope -- ``mcp.http.example.json`` is Future Work
only and this module never reads it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_SERVERS = ("jamf", "intune", "servicenow")
_PLACEHOLDER_MARKER = "OPERATOR_SUPPLY"


@dataclass(frozen=True)
class McpConfigStatus:
    configured: bool
    reason: str
    servers: dict[str, dict[str, Any]]


def _is_placeholder(server: dict[str, Any]) -> bool:
    command = str(server.get("command", ""))
    args = server.get("args", [])
    if _PLACEHOLDER_MARKER in command:
        return True
    return any(_PLACEHOLDER_MARKER in str(arg) for arg in args)


def load_mcp_config(path: Path) -> McpConfigStatus:
    """Return whether the operator has filled in real stdio command/args for
    every required server. Never fabricates a command/args pair."""
    if not path.is_file():
        return McpConfigStatus(
            configured=False,
            reason=(
                f"MCP_SERVERS_CONFIG not found at {path}. Copy "
                "session-host/config/mcp.stdio.example.json to mcp.stdio.json and fill in the "
                "real stdio command/args for jamf, intune, and servicenow from the operator's "
                "Claude Code MCP config (no secret values)."
            ),
            servers={},
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return McpConfigStatus(configured=False, reason=f"MCP_SERVERS_CONFIG is not valid JSON: {exc}", servers={})

    servers = payload.get("mcpServers", {})
    missing = [name for name in REQUIRED_SERVERS if name not in servers]
    if missing:
        return McpConfigStatus(
            configured=False,
            reason=f"MCP_SERVERS_CONFIG is missing server(s): {', '.join(missing)}.",
            servers=servers,
        )

    placeholders = [name for name in REQUIRED_SERVERS if _is_placeholder(servers[name])]
    if placeholders:
        return McpConfigStatus(
            configured=False,
            reason=(
                f"MCP_SERVERS_CONFIG still has <OPERATOR_SUPPLY> placeholders for: "
                f"{', '.join(placeholders)}. Paste the real stdio command/args from the "
                "operator's Claude Code MCP config (~/.claude.json or project .mcp.json)."
            ),
            servers=servers,
        )

    return McpConfigStatus(configured=True, reason="", servers=servers)
