"""General-purpose chat turn via the Claude Agent SDK (product pivot
2026-08-31 -- see backend.md Audit).

Earlier revisions of this host routed every message through a deterministic
regex/stopword preprocessor that picked between exactly two hardcoded modes
(``device_lookup`` / ``asset_ops``) and rejected anything that did not parse
as a bare identity list. The actual goal is simpler and bigger: "Claude, but
with my skills and MCP tools already attached" for colleagues who should
never have to set up a dev environment. So this module drops the mode
router entirely -- every message is one turn of one general chat session
that has:

  - Every MCP server the operator has registered in their own Claude Code
    config (``~/.claude.json`` by default -- see ``Settings.claude_config_path``),
    not a curated 3-server subset. Full parity, not a curated slice.
  - One custom in-process tool, ``build_asset_report``, wrapping this
    package's existing deterministic asset-ops pipeline (fixed subprocess
    argv, no shell string -- see ``asset_ops.py``) so the model can invoke it
    on its own judgment instead of a preprocessor deciding for it up front.
  - Multi-turn memory via context-stuffing prior turns into the prompt
    (``runs.RunStore.get_thread_history``/``append_thread_history``), not the
    SDK's own ``resume``. ``resume`` was tried first and rejected live
    2026-08-31: the session id round-trips correctly, but resuming fails with
    "No conversation found with session ID: ..." every time, because it
    depends on Anthropic's own server-side session persistence -- which a
    third-party LiteLLM gateway (this deployment's ``ANTHROPIC_BASE_URL``)
    does not implement.

Deliberately does NOT enable raw ``Bash``/``Read``/``Write``/``Edit``. This
repo's own two skills (device lookup, asset reporting) are already
implemented safely without them (MCP tool calls, or a fixed-argv subprocess).
The operator's *personal* Claude Code skills under ``docs/.claude/skills/``
and ``~/.claude/skills/`` are written for a different, personal workspace
(``~/work``, which does not exist on a shared host) and in at least one case
(a Jamf static-group "replace" sync) are explicitly documented as a
destructive full-overwrite -- not something to hand unauthenticated
local-network colleagues raw shell access to. See backend.md Known Gaps for
the full reasoning; revisit if the operator explicitly wants that widened.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .asset_ops import run_asset_ops
from .runs import Turn
from .settings import Settings

CHAT_SYSTEM_PROMPT = (
    "You are the Fleet Recon assistant for the CPE fleet team. You have the operator's "
    "full set of MCP tools attached (ServiceNow, Jamf, Intune, Tenable, Atlassian, Slack, "
    "Google Workspace, and anything else registered), plus one custom tool, "
    "`build_asset_report`, for turning a pasted username/email list or an uploaded CSV into "
    "a device-grained asset report (ServiceNow hardware + Jamf/Intune MDM status, one row "
    "per device). Use whichever tools the request actually calls for -- a single serial, "
    "hostname, or username is usually a direct MCP lookup; a list of people or a CSV is "
    "usually `build_asset_report`. Never invent data you did not get from a tool call, and "
    "say plainly when a tool call fails or comes back empty rather than guessing."
)

DISALLOWED_TOOLS: tuple[str, ...] = ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch")


@dataclass(frozen=True)
class ChatResult:
    status: str  # "completed" | "failed"
    diagnostic: str | None
    text: str | None


def _friendly_tool_name(name: str) -> str:
    """``mcp__jamf__get_computer_by_username`` -> ``Jamf -> get_computer_by_username``.

    MCP tools are namespaced by the CLI as ``mcp__<server>__<tool>``; strip
    that down to something worth putting in front of someone watching a live
    activity feed instead of a raw wire-format tool name."""
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        if len(parts) == 3:
            _, server, tool = parts
            return f"{server} -> {tool}"
    return name


def _describe_tool_use(block: Any) -> str:
    if str(block.name).endswith("build_asset_report"):
        return "Building the asset report..."
    return f"Calling {_friendly_tool_name(block.name)}..."


def _describe_tool_result(block: Any) -> str:
    return "Tool call failed -- see the final response for detail." if block.is_error else "Got a result back."


def _render_history(history: list[Turn], prompt: str) -> str:
    """Context-stuffing, not the SDK's `resume` -- see module docstring for
    why. Renders prior turns as a plain transcript ahead of the new message;
    ``RunStore`` already caps how many turns are kept."""
    if not history:
        return prompt
    lines = [f"{'User' if role == 'user' else 'Assistant'}: {text}" for role, text in history]
    return (
        "Conversation so far (for your context -- do not repeat it back verbatim):\n"
        + "\n\n".join(lines)
        + f"\n\n---\n\nNew message from the user: {prompt}"
    )


def _load_mcp_servers(claude_config_path: Path) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Mirror the operator's own Claude Code MCP registrations 1:1. Never
    fabricates a server entry; an empty/missing config is a Diagnostic."""
    if not claude_config_path.is_file():
        return {}, (
            f"No Claude Code config found at {claude_config_path}. Set CLAUDE_CONFIG_PATH "
            "to a ~/.claude.json (or equivalent) that has your mcpServers registered."
        )
    try:
        payload = json.loads(claude_config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, f"{claude_config_path} is not valid JSON: {exc}"

    raw_servers = payload.get("mcpServers", {})
    servers: dict[str, dict[str, Any]] = {}
    for name, entry in raw_servers.items():
        if not isinstance(entry, dict) or not entry.get("command"):
            continue
        servers[name] = {
            "type": entry.get("type", "stdio"),
            "command": entry["command"],
            "args": entry.get("args", []),
            "env": entry.get("env", {}),
        }
    if not servers:
        return {}, f"{claude_config_path} has no usable mcpServers entries."
    return servers, None


def _build_asset_report_tool(settings: Settings, run_id: str) -> Any:
    import claude_agent_sdk as sdk

    @sdk.tool(
        "build_asset_report",
        "Turn a pasted username/email list, or a previously uploaded CSV, into a "
        "device-grained asset report: ServiceNow hardware plus Jamf/Intune MDM enrollment, "
        "one row per device. Use for multiple people or a CSV -- for exactly one "
        "serial/hostname/username, call the ServiceNow/Jamf/Intune MCP tools directly "
        "instead, it's faster.",
        {
            "usernames": list[str],
            "csv_path": str,
        },
    )
    async def build_asset_report(args: dict[str, Any]) -> dict[str, Any]:
        usernames = [str(u).strip() for u in (args.get("usernames") or []) if str(u).strip()]
        csv_path = str(args.get("csv_path") or "").strip()
        csv_bytes: bytes | None = None
        if csv_path:
            path = Path(csv_path)
            if not path.is_file():
                return {
                    "content": [{"type": "text", "text": f"No file found at {csv_path}."}],
                    "is_error": True,
                }
            csv_bytes = path.read_bytes()
        if not usernames and csv_bytes is None:
            return {
                "content": [{"type": "text", "text": "Provide either usernames or csv_path."}],
                "is_error": True,
            }

        result = run_asset_ops(run_id, settings, identities=usernames or None, csv_bytes=csv_bytes)
        if result.status == "failed":
            return {
                "content": [{"type": "text", "text": result.diagnostic or "asset report failed."}],
                "is_error": True,
            }

        preview = result.csv_preview or {}
        caveat = f" (partial -- {result.diagnostic})" if result.diagnostic else ""
        summary = (
            f"{preview.get('row_count', 0)} device row(s) written to "
            f"{preview.get('filename', 'the report')}{caveat}.\n\n"
            f"First {len(preview.get('preview_rows', []))} row(s):\n"
            f"{json.dumps(preview.get('preview_rows', []), indent=2)}"
        )
        return {"content": [{"type": "text", "text": summary}]}

    return sdk.create_sdk_mcp_server("fleet_recon", tools=[build_asset_report])


async def run_chat_turn(
    run_id: str,
    prompt: str,
    settings: Settings,
    history: list[Turn] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ChatResult:
    """Run one turn of a general chat session. ``history`` (prior turns of
    the same ``thread_id``, from ``RunStore.get_thread_history``) is stuffed
    into the prompt for continuity -- see module docstring for why this is
    not the SDK's own ``resume``. ``on_progress``, if given, is called
    synchronously with a short human-readable line each time the SDK reports
    a tool call or tool result, so a caller can surface a live activity feed
    instead of a static "thinking" spinner (see backend.md Audit 2026-08-31)."""
    if not settings.anthropic_base_url or not settings.litellm_model:
        return ChatResult(
            status="failed",
            diagnostic=(
                "ANTHROPIC_BASE_URL and/or LITELLM_MODEL are not set. Fill in the LiteLLM "
                "gateway values in .env before chatting."
            ),
            text=None,
        )

    import claude_agent_sdk as sdk

    mcp_servers, mcp_error = _load_mcp_servers(settings.claude_config_path)
    if mcp_error:
        return ChatResult(status="failed", diagnostic=mcp_error, text=None)

    mcp_servers = dict(mcp_servers)
    mcp_servers["fleet_recon"] = _build_asset_report_tool(settings, run_id)

    options = sdk.ClaudeAgentOptions(
        system_prompt=CHAT_SYSTEM_PROMPT,
        mcp_servers=mcp_servers,
        disallowed_tools=list(DISALLOWED_TOOLS),
        # Headless host, no human to click "allow" -- see module docstring for
        # why raw Bash/filesystem tools are withheld instead of gated per-call.
        permission_mode="bypassPermissions",
        # "project" only (not "user"): this repo has no .claude/settings.json or
        # CLAUDE.md to load, so this is not pulling in the operator's personal
        # skills (see module docstring) -- but bare [] turned out to be full SDK
        # isolation mode, which also silently disabled the CLI's own session
        # transcript persistence, breaking `resume` ("No conversation found with
        # session ID: ..." on every second turn). Confirmed live 2026-08-31.
        setting_sources=["project"],
        strict_mcp_config=True,
        model=settings.litellm_model,
        max_turns=30,
        env={
            "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
            "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        },
    )

    full_prompt = _render_history(history or [], prompt)

    transcript_parts: list[str] = []
    drafting_announced = False
    try:
        async for message in sdk.query(prompt=full_prompt, options=options):
            if isinstance(message, sdk.AssistantMessage):
                for block in message.content:
                    if isinstance(block, sdk.ToolUseBlock):
                        drafting_announced = False
                        if on_progress:
                            on_progress(_describe_tool_use(block))
                    elif isinstance(block, sdk.TextBlock):
                        transcript_parts.append(block.text)
                        if on_progress and not drafting_announced:
                            on_progress("Drafting the response...")
                            drafting_announced = True
            elif isinstance(message, sdk.UserMessage) and isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, sdk.ToolResultBlock) and on_progress:
                        on_progress(_describe_tool_result(block))
    except Exception as exc:  # noqa: BLE001 - surfaced as a Diagnostic, not a crash
        return ChatResult(status="failed", diagnostic=f"chat session failed: {exc}", text=None)

    summary = "\n".join(transcript_parts).strip()
    if not summary:
        return ChatResult(
            status="failed",
            diagnostic="The session ended without a text response.",
            text=None,
        )

    return ChatResult(status="completed", diagnostic=None, text=summary)
