"""Single-identifier lookup via the Claude Agent SDK (SAD §2.4/§2.5, PRD FR-2,
docs/.claude/skills/device-lookup/SKILL.md).

Locks ``allowed_tools`` to the device-lookup tool set and enforces it a
second time with a ``PreToolUse`` hook, so the model cannot expand its own
tool access, add Cortex/Tenable, or reach for unconstrained Bash. Runs only
after skill bind has already decided ``mode == "device_lookup"`` -- one
identifier, no list, no CSV.

``claude_agent_sdk`` is imported lazily inside the functions that need it so
this module (and the rest of the host) can be imported and unit-tested even
in an environment where the SDK is not resolvable, and so the MCP-placeholder
Diagnostic path never requires a real model call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mcp_config import McpConfigStatus, load_mcp_config
from .preprocessor import is_vuln_phrasing
from .settings import Settings

# docs/.claude/skills/device-lookup/SKILL.md tool execution matrix. MCP tools
# are always registered by the Claude Code CLI as `mcp__<server>__<tool>`
# (server names below must match the keys _build_mcp_servers emits: jamf,
# intune, servicenow) -- the bare tool name is never callable, and a
# PreToolUse hook keyed on the bare name denies the real tool every time.
ALLOWED_TOOLS: tuple[str, ...] = (
    "mcp__jamf__jamf_get_device_summary",
    "mcp__intune__intune_lookup_device",
    "mcp__servicenow__snow_lookup_user_profile",
)

DEVICE_LOOKUP_SYSTEM_PROMPT = (
    "You resolve exactly one serial number, hostname, or username to device/user context "
    "using only the tools you have been given. Call the primary tool immediately -- do not "
    "ask for confirmation or tool selection. Reply with a short conversational summary: "
    "OS/build, compliance status, last check-in, and assigned user when available. "
    "Never invent data you did not receive from a tool call."
)


@dataclass(frozen=True)
class DeviceLookupResult:
    status: str  # "completed" | "failed"
    diagnostic: str | None
    card: dict[str, Any] | None


def _pretooluse_hook(allowed: frozenset[str]):
    async def _hook(input_data, tool_use_id, context):  # noqa: ANN001 - SDK-defined shapes
        tool_name = input_data.get("tool_name", "")
        if tool_name in allowed:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                }
            }
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Tool '{tool_name}' is not in the device-lookup allowlist "
                    f"({', '.join(sorted(allowed))})."
                ),
            }
        }

    return _hook


def _build_mcp_servers(mcp_status: McpConfigStatus) -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for name, entry in mcp_status.servers.items():
        if name not in ("jamf", "intune", "servicenow"):
            continue
        servers[name] = {
            "type": "stdio",
            "command": entry["command"],
            "args": entry.get("args", []),
            "env": entry.get("env", {}),
        }
    return servers


async def run_device_lookup(identifier: str, raw_text: str, settings: Settings) -> DeviceLookupResult:
    """Run the Agent SDK session for exactly one identifier.

    Returns a clear Diagnostic (never a stack trace, never a fabricated
    lookup) when the operator has not yet filled in real MCP stdio config,
    or when the phrasing asks for a vulnerability assessment (Tenable is not
    wired up for this skill; see backend.md Open Questions).
    """
    if is_vuln_phrasing(raw_text):
        return DeviceLookupResult(
            status="failed",
            diagnostic=(
                "Vulnerability-assessment phrasing detected. Tenable is not part of this "
                "skill's MVP tool set (docs/.claude/skills/device-lookup/SKILL.md scopes "
                "Tenable to vuln phrasing, but no Tenable MCP server is configured for Fleet "
                "Recon). Not implemented."
            ),
            card=None,
        )

    mcp_status = load_mcp_config(settings.mcp_servers_config)
    if not mcp_status.configured:
        return DeviceLookupResult(status="failed", diagnostic=mcp_status.reason, card=None)

    if not settings.anthropic_base_url or not settings.litellm_model:
        return DeviceLookupResult(
            status="failed",
            diagnostic=(
                "ANTHROPIC_BASE_URL and/or LITELLM_MODEL are not set. Fill in the LiteLLM "
                "gateway values in .env before running device_lookup."
            ),
            card=None,
        )

    import claude_agent_sdk as sdk  # local import: see module docstring

    allowed = frozenset(ALLOWED_TOOLS)
    options = sdk.ClaudeAgentOptions(
        system_prompt=DEVICE_LOOKUP_SYSTEM_PROMPT,
        allowed_tools=list(ALLOWED_TOOLS),
        disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch"],
        mcp_servers=_build_mcp_servers(mcp_status),
        # Without these two, the CLI subprocess also auto-discovers the
        # operator's own ~/.claude.json (project/user settings and every
        # other locally-registered MCP server) and merges it in alongside
        # the 3 servers above -- burning max_turns on a much larger tool
        # surface than this skill is supposed to expose, even though
        # PreToolUse would still deny the call. Keep this session's tools
        # limited to exactly what device_lookup declares.
        strict_mcp_config=True,
        setting_sources=[],
        hooks={"PreToolUse": [sdk.HookMatcher(hooks=[_pretooluse_hook(allowed)])]},
        model=settings.litellm_model,
        # Even with the correct tool names, the model reliably burns 1-2 turns
        # on a denied ToolSearch attempt before calling the primary tool
        # directly (observed live), plus occasional argument-name retries.
        # 6 leaves zero margin (observed exactly num_turns=6 on a single-
        # device serial lookup); 10 leaves room for a username that fans out
        # to ServiceNow + Jamf/Intune without changing the one-identifier
        # scope of this skill.
        max_turns=10,
        env={
            "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
            "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        },
    )

    transcript_parts: list[str] = []
    try:
        async for message in sdk.query(prompt=identifier, options=options):
            text_block = getattr(message, "content", None)
            if not text_block:
                continue
            for block in text_block:
                text = getattr(block, "text", None)
                if text:
                    transcript_parts.append(text)
    except Exception as exc:  # noqa: BLE001 - surfaced as a Diagnostic, not a crash
        return DeviceLookupResult(
            status="failed", diagnostic=f"device_lookup session failed: {exc}", card=None
        )

    summary = "\n".join(transcript_parts).strip()
    if not summary:
        return DeviceLookupResult(
            status="failed", diagnostic="device_lookup returned no summary from the model.", card=None
        )

    return DeviceLookupResult(
        status="completed",
        diagnostic=None,
        card={"type": "chat.device_card", "identifier": identifier, "summary": summary},
    )
