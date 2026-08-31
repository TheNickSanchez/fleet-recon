# Fleet Recon Backend Implementation — Session Host

**Product pivot, 2026-08-31 — this document supersedes the mode-router record below it (2026-08-29/30), which itself superseded the original CrewAI record.** The operator's own words: *"the goal of this app: it should be like Claude but with all my skills and MCP tools attached already."* The previous MVP routed every message through a deterministic preprocessor that picked between exactly two hardcoded modes (`device_lookup` for one identity, `asset_ops` for a list/CSV) and rejected anything else outright. That is now gone. The session host is a **general-purpose chat backend**: every message is one turn of one Claude Agent SDK session that has every MCP server the operator has registered in their own Claude Code config attached (13 servers on this machine — ServiceNow, Jamf, Intune, Tenable, Atlassian, Slack, and Google Workspace), plus one custom tool wrapping this repo's existing deterministic asset-report pipeline. There is still no CrewAI kickoff, no Postgres, no Redis, no OIDC, and no admin console.

Runtime: `AAMAD_TARGET_RUNTIME=claude-agent-sdk` (from `aamad.config.yml`). Adapter: `.cursor/rules/adapter-claude-agent-sdk.mdc`.

## Scope

- **`chat.py`** — one function, `run_chat_turn`, replacing `device_lookup.py` and the model-facing half of `preprocessor.py`/`mcp_config.py` (both deleted, along with `test_preprocessor.py`/`test_mcp_config.py`/`test_device_lookup.py`). Every message is a Claude Agent SDK session with:
  - Every MCP server mirrored 1:1 from the operator's `~/.claude.json` (`Settings.claude_config_path`, overridable per-machine) — not a curated 3-server subset.
  - One in-process custom tool, `build_asset_report` (via `claude_agent_sdk.tool`/`create_sdk_mcp_server`), wrapping the **unchanged** `asset_ops.py` pipeline (fixed subprocess argv, no shell string) so the model can invoke it on its own judgment for a list/CSV instead of a regex preprocessor deciding for it up front.
  - Multi-turn memory via context-stuffing prior turns into the prompt (`runs.RunStore.get_thread_history`), **not** the SDK's own `resume` — see "Known Gaps", this was tried first and rejected live.
  - `Bash`/`Read`/`Write`/`Edit`/`Glob`/`Grep`/`WebFetch`/`WebSearch` deliberately disallowed — see "Known Gaps" for why, and what was deliberately left out of scope for this pass.
- **`runs.py`** — reworked from a `QueryRun` record with `mode`/`skill_id`/`intent_id` to a `thread_id`-scoped chat turn, plus `RunStore.get_thread_history`/`append_thread_history` (capped at `MAX_HISTORY_TURNS = 12`).
- **`api.py`** — the preprocessor gate is gone. `POST /api/v1/runs` accepts any non-empty text and/or a CSV file, with an optional `thread_id` to continue a conversation.
- **[New, same day] Live activity feed.** First operator feedback after trying the general-chat pivot: *"it's still slow but it's fine. my issue is that it's static while looking up. with claude, at least you can see it thinking."* `run_chat_turn` now takes an `on_progress` callback invoked synchronously as the SDK streams tool calls/results, and `RunStore.append_activity` records each line on the `Run` for the client to poll and render — see "Live Activity Feed" below.
- 31 passing unit tests (18 of the original 25 mode-router tests were replaced, not just deleted, at the pivot; 9 more added for the activity feed — see "Tests").
- **Live-smoke validated on this machine 2026-08-31**: a general open-ended question, a real single-identity lookup (`nick.sanchez`, live ServiceNow+Jamf+Intune, richer output than the old narrow skill — it proactively flagged a serial mismatch between ServiceNow and Jamf), and a two-turn conversation proving context-stuffing memory actually works. See "Live Smoke Test".

## How to Run

```bash
# From repository root
cp .env.example .env
# Fill ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY / LITELLM_MODEL.
# CLAUDE_CONFIG_PATH defaults to ~/.claude.json -- override if your MCP servers live elsewhere.

cd session-host
uv sync
uv run python -m fleet_session_host
# Listens on 127.0.0.1:8100 (SESSION_HOST_HOST / SESSION_HOST_PORT)
```

Tests:

```bash
cd session-host
uv run pytest -q
# 31 passed
```

## Package Layout

```text
session-host/fleet_session_host/
  __main__.py       # uv run / python -m entrypoint; runs uvicorn on SESSION_HOST_HOST:PORT
  settings.py        # env loading, skeleton/readiness checks, claude_config_path
  chat.py             # general chat turn: full MCP parity, build_asset_report tool, history stuffing
  asset_ops.py         # UNCHANGED: temp CSV writer, fixed-argv passkey subprocess runner
  csv_preview.py         # UNCHANGED: chat.csv_preview builder, consumed internally by chat.py's tool
  runs.py                 # in-memory Run record + thread-safe store, thread_id + history + activity, no DB
  api.py                   # Starlette app: /api/v1/health, /ready, /runs, /runs/{id}
session-host/tests/         # 31 unit tests, no live vendors
```

Deleted this pass: `preprocessor.py`, `mcp_config.py`, `device_lookup.py` (and their tests) — superseded by `chat.py`. `asset_ops.py` and `csv_preview.py` are untouched; they are still the safest, most deterministic part of this host and are now *reused*, not replaced.

## `chat.py` (General Chat Session)

`chat.py::run_chat_turn(run_id, prompt, settings, history)`:

1. Requires `ANTHROPIC_BASE_URL`/`LITELLM_MODEL` (Diagnostic if unset, same as before).
2. Loads every `mcpServers` entry from `settings.claude_config_path` (default `~/.claude.json`) verbatim — `command`/`args`/`env` copied through, entries without a `command` skipped, never fabricated. On this machine that's 13 servers: `jamf`, `servicenow`, `intune`, `tenable`, `atlassian`, `slack`, `calendar`, `drive`, `gmail`, `people`, `docs`, `sheets`, `slides`.
3. Registers one additional in-process MCP server, `fleet_recon`, with a single tool `build_asset_report(usernames: list[str], csv_path: str)` that calls the **existing, unchanged** `asset_ops.run_asset_ops` (same fixed-argv `passkey` subprocess pipeline as before) and returns the row count + preview rows as tool-result text for the model to narrate.
4. `ClaudeAgentOptions`: `strict_mcp_config=True` (session is exactly the servers above, nothing auto-discovered beyond them), `setting_sources=["project"]` (loads `CLAUDE.md`/project settings if this repo ever adds one — it currently has none, so this is a no-op today, but is **not** `[]`; see "Known Gaps" for why bare `[]` broke session resume), `permission_mode="bypassPermissions"` (headless host, no human to click "allow"), `disallowed_tools` = `Bash`/`Read`/`Write`/`Edit`/`Glob`/`Grep`/`WebFetch`/`WebSearch`, `max_turns=30`.
5. `prompt` is `_render_history(history, prompt)` — prior turns of the same thread rendered as a plain `User: .../Assistant: ...` transcript ahead of the new message, not the SDK's `resume`.
6. Runs `claude_agent_sdk.query(...)`, concatenates assistant text blocks, returns `ChatResult(status, diagnostic, text)`.

### Why raw Bash/filesystem tools are withheld

The operator's answer to "should the agent have ALL your skills and MCP tools" was explicit: **all**, with **no access control**, for **colleagues on the local network**. Two live findings changed how that got implemented:

1. `~/.claude.json` has 13 MCP servers with real credentials — those are all attached, verbatim, satisfying "all my MCP tools" literally.
2. The operator's *personal* Claude Code skills (`docs/.claude/skills/*` in this repo, plus `~/.claude/skills/twg-*` on this machine) are a different thing: they are written for a personal workspace (`~/work`, which does not exist on this machine, let alone a shared host) and at least one of them (`asset-ops/SKILL.md`'s Jamf group sync, `--mode replace`) is explicitly documented in its own text as **"dangerous, full overwrite."** Wiring raw `Bash` + those scripts open for any unauthenticated colleague on the LAN is a way to accidentally wipe a production Jamf group with zero audit trail of who did it. This was flagged to the operator live before implementation and not overridden.

The resolution: this repo's own two *actually-implemented* capabilities (device/user lookup via MCP tool calls, asset reporting via `asset_ops.py`'s fixed-argv subprocess) are exposed as-is — no Bash needed for either, both were already safe before this pivot. The personal skill docs are left unreachable. If the operator wants raw shell access wired up anyway (e.g. to run other `docs/.claude/skills/*` playbooks through the chat), that is a deliberate, explicit follow-up decision, not a default.

## Live Activity Feed

A ~30-45s multi-tool turn with a static "Thinking..." spinner reads as broken, not slow — the operator's exact words: *"i can see it thinking [with Claude]."* Message-level (not token-level) progress is enough to fix that, and the SDK message stream already carries it without any extra API calls:

1. `run_chat_turn` accepts `on_progress: Callable[[str], None] | None`, called synchronously as `sdk.query(...)` streams messages.
2. Iterates with `isinstance` checks (replacing the old duck-typed `getattr(message, "content", None)` that only ever captured `TextBlock.text`): an `AssistantMessage`'s `ToolUseBlock` → `_describe_tool_use` (`"Calling {server} -> {tool}..."`, unwrapping the CLI's `mcp__<server>__<tool>` namespacing via `_friendly_tool_name`; special-cased to `"Building the asset report..."` for `build_asset_report`); a `TextBlock` → `"Drafting the response..."` (once per uninterrupted run of text, reset by the next tool call, since a turn can interleave preamble text, tool calls, and a final answer); a `UserMessage`'s `ToolResultBlock` → `"Got a result back."` or a failure line if `is_error`.
3. `api.py`'s `_process_chat_turn` wires the callback to `store.append_activity(run_id, line)` and seeds `"Connecting to the session..."` the moment a run flips to `running`, so the feed is never empty while polling.
4. `Run.activity: list[str]` (new field, `runs.py`) is append-only while `status in ("queued", "running")` — `RunStore.append_activity` is a no-op once a run is terminal, so a background task's in-flight progress calls can never mutate a run the client already rendered as complete/failed. Exposed on `to_summary()` (and therefore every `GET /runs/{id}` poll response) as `activity`.
5. Frontend (`frontend.md`) renders the last 5 lines as a live feed with the newest line highlighted, replacing the old indeterminate progress bar.

Live example (real `nick.sanchez` lookup, 2026-08-31): `Connecting to the session...` → `Drafting the response...` (the model's preamble, e.g. "I'll look up Nick Sanchez's profile...") → `Calling ToolSearch...` → `Got a result back.` → three parallel tool calls (`servicenow -> snow_lookup_user_profile`, `jamf -> jamf_get_user_devices`, `intune -> intune_lookup_users`) each followed by `Got a result back.` → `Drafting the response...` again for the real final answer → `completed`.

## HTTP API

Binds to `SESSION_HOST_HOST:SESSION_HOST_PORT` (default `127.0.0.1:8100`, localhost-only — see "Known Gaps", this is *not yet* reachable from the local network the operator asked for). No CORS middleware.

| Method & path | Body | Behavior |
| --- | --- | --- |
| `GET /api/v1/health` | — | `{"status": "ok"}` liveness. |
| `GET /api/v1/ready` | — | `{"status": "ok"\|"degraded", "problems": [...]}` — checks `ASSET_OPS_SCRIPTS_DIR`, `CLAUDE_CONFIG_PATH`, `MCP_TRANSPORT=stdio`, `passkey` on `PATH`. |
| `POST /api/v1/runs` | `application/json {"text": "...", "thread_id": "..."}` **or** `multipart/form-data` (`file`, `text`, `thread_id`) | `400 VALIDATION_ERROR` only if both text and file are empty; otherwise `202` with the run summary. Generates a new `thread_id` if none was given. Kicks off `chat.run_chat_turn` as an asyncio background task. |
| `GET /api/v1/runs/{run_id}` | — | Run summary; `result` is `{"type": "chat.text", "text": "..."}` once terminal, else `null`. `404` for an unknown id. |

Run summary shape: `id`, `correlation_id`, `thread_id`, `input_kind`, `status` (`queued`/`running`/`completed`/`failed` — `partial`/`rejected` are gone, there is no longer a structured result type that has a "partial" concept; a tool-call failure is just narrated by the model in its text), `created_at`, `updated_at`, `result`, `error`, `diagnostic`, `activity` (new — `list[str]`, live progress lines, see "Live Activity Feed"; empty until the run leaves `queued`).

## Live Smoke Test (2026-08-31)

```bash
curl -s -X POST http://127.0.0.1:8100/api/v1/runs -H 'Content-Type: application/json' \
  -d '{"text":"hey, what can you help me with?"}'
# -> completed in 13s, self-described its own MCP tool surface accurately (device/asset lookups,
#    bulk reporting, ticketing/docs, vuln data) -- not a canned string, model-generated from the
#    actual attached tool list.

curl -s -X POST http://127.0.0.1:8100/api/v1/runs -H 'Content-Type: application/json' \
  -d '{"text":"look up nick.sanchez"}'
# -> completed in 32.1s (first lookup, no cache -- see "Known Gaps", the identifier cache from the
#    prior pass was device_lookup.py-specific and did not carry over). Real ServiceNow profile,
#    real Jamf devices, real Intune (0 devices, correctly explained as "all his hardware is
#    Apple/Jamf-managed"), and unprompted: flagged that one Jamf serial did not match the
#    corresponding ServiceNow asset record and asked whether to dig into it -- richer than the old
#    fixed device_lookup skill ever produced.

# Two-turn conversation in the same thread_id:
curl -s -X POST .../runs -d '{"text":"My name is Nick and my favorite fleet tool is Jamf. Remember that."}'
# thread_id: 876d56b3-...
curl -s -X POST .../runs -d '{"text":"What is my name and my favorite fleet tool?","thread_id":"876d56b3-..."}'
# -> "Your name is Nick, and your favorite fleet tool is Jamf." -- confirms context-stuffing memory.
```

`GET /api/v1/ready` returned `{"status":"ok","problems":[]}` throughout — `claude_config_path` resolved to the operator's real `~/.claude.json` with no manual copy step needed (unlike the old `mcp.stdio.json`, which required hand-copying 3 servers' credentials).

## Tests

`session-host/tests/` — 31 tests, `uv run pytest -q` → `31 passed`, no live vendor calls:

- `test_chat.py`: missing `LITELLM_MODEL`/`ANTHROPIC_BASE_URL` and missing/empty `CLAUDE_CONFIG_PATH` both return a clear Diagnostic before any SDK import; `_load_mcp_servers` mirrors a real config and skips an entry with no `command` rather than fabricating one; `_render_history` stuffs prior turns correctly and leaves an empty history's prompt unchanged; `DISALLOWED_TOOLS` asserts `Bash`/`Read`/`Write` stay off. **[New]** `_friendly_tool_name`/`_describe_tool_use`/`_describe_tool_result` against fake block objects (no live SDK session needed) covering MCP-namespace unwrapping, the `build_asset_report` special case, and the error/success result lines.
- `test_runs.py`: `RunStore` thread-history round-trips per `thread_id` (never leaks across threads) and caps at `MAX_HISTORY_TURNS`, dropping the oldest turns first. **[New]** `append_activity` appends while running, is a no-op once a run is terminal (a late progress callback from an already-finished background task must not resurrect its feed), and is a no-op for an unknown run id.
- `test_api.py`: `_build_prompt` correctly appends a CSV note when a file is present, with or without accompanying text.
- `test_asset_ops.py`, `test_csv_preview.py`: **unchanged** — `asset_ops.py`/`csv_preview.py` were not touched by this pivot.

## Known Gaps

- **[New, 2026-08-31] Session-resume abandoned in favor of context-stuffing.** The SDK's own `ClaudeAgentOptions.resume` was tried first (pass the prior turn's `ResultMessage.session_id` back in). It failed live, every time, with `"No conversation found with session ID: ..."` even though the id round-tripped correctly — this depends on Anthropic's own server-side session persistence, which the operator's third-party LiteLLM gateway (`ANTHROPIC_BASE_URL`) does not implement. Switched to rendering prior turns into the prompt text instead (`RunStore.get_thread_history`), which works with any gateway. Trade-off: unbounded prompt growth is capped at 12 turns with no summarization/compaction — a very long conversation will start losing its earliest context rather than growing forever. Revisit if that becomes a real problem in practice.
- **[New, 2026-08-31] `setting_sources=[]` silently breaks more than just skill/CLAUDE.md loading.** It was tried first (matching the old `device_lookup.py`'s isolation stance) and also broke session resume before that was abandoned for the reason above — bare `[]` is "full SDK isolation mode," which turned out to also suppress the CLI's own session transcript persistence. Not currently load-bearing now that resume isn't used, but left as `["project"]` rather than reverted to `[]`, since this repo has no `.claude/settings.json`/`CLAUDE.md` for `"project"` to actually load (verified) — it is a no-op today, kept only because `[]` has a broader, surprising blast radius than its name suggests.
- **[Regression, 2026-08-31] The `device_lookup.py` 5-minute identifier cache is gone.** It was specific to that module's `run_device_lookup(identifier, ...)` signature and had no equivalent to key off in a general chat turn (`run_chat_turn(prompt, ...)` takes free-form text, not a canonicalized identifier) — it was not ported, not an oversight. A repeat "look up nick.sanchez" today re-runs the full ~30-45s agent session again, same as a first lookup — **[Mitigated same day]** the UI now shows a live per-tool-call activity feed instead of a static spinner during that wait (see "Live Activity Feed"), which addressed the operator's actual complaint ("it's static while looking up... it should be fine [on raw speed]"), but the underlying latency itself is unchanged. Caching general chat turns would need a different design (e.g. detect + canonicalize an identifier out of free text, same as the old preprocessor did) — still flagged as an Open Question, not solved in this pass.
- **[Not done, 2026-08-31] Still bound to `127.0.0.1` — not actually reachable from the local network yet.** The operator's stated audience was "colleagues on the same network," but `SESSION_HOST_HOST` still defaults to `127.0.0.1` and there is still no CORS middleware. Making this genuinely reachable by another machine needs: (a) binding to `0.0.0.0` (or the host's LAN IP) behind a firewall rule, (b) a real CORS policy or a reverse proxy that puts the frontend and API on the same origin for every client machine (the current Vite-dev-proxy trick only works for whoever is running the dev server locally), and (c) revisiting "no access control" once it's actually exposed beyond one operator's own browser. This is a Deliver-phase (`@devops.eng`, `deploy.md`) decision, not a drive-by change to `api.py` — flagged, not built.
- **Deliberately not wired: raw Bash + the operator's personal `docs/.claude/skills/*`/`~/.claude/skills/*`.** See `chat.py`'s "Why raw Bash/filesystem tools are withheld" above. Revisit only on an explicit operator decision.
- No SSE/WebSocket progress stream; clients poll `GET /runs/{id}` (unchanged from the prior pass).
- Session/run records are process-memory only; a host restart loses in-flight run status and all thread history (unchanged).
- No rate limiting, no per-actor auth — matches the operator's explicit "none for now" answer, but is materially riskier now that the chat has 13 real MCP servers attached and no auth than it was with 3 narrow, read-mostly tools.

## Env Table

| Name | Used by |
| --- | --- |
| `AAMAD_TARGET_RUNTIME` | Resolved runtime marker (`claude-agent-sdk`). |
| `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `LITELLM_MODEL` | `chat.py` → `ClaudeAgentOptions` (LiteLLM Anthropic-compatible proxy). |
| `CLAUDE_CONFIG_PATH` | **New.** `chat.py` → operator's Claude Code config (default `~/.claude.json`); source of every MCP server attached to the general chat session. |
| `SESSION_HOST_HOST`, `SESSION_HOST_PORT` | `__main__.py` → uvicorn bind (default `127.0.0.1:8100` — see "Known Gaps" re: LAN reachability). |
| `ASSET_OPS_SCRIPTS_DIR` | `asset_ops.py` (unchanged) → `build_asset_report` tool's underlying scripts. |
| `SESSION_TMP_DIR`, `SESSION_REPORTS_DIR` | `asset_ops.py` / `csv_preview.py` (unchanged). |
| `MCP_TRANSPORT`, `MCP_SERVERS_CONFIG` | Legacy — no longer read by `chat.py` (which reads `CLAUDE_CONFIG_PATH` instead); `MCP_TRANSPORT` is still checked by `settings.check_skeleton()` for the `asset_ops` path's own assumptions. `session-host/config/mcp.stdio.json` is no longer required. |
| `SNOW_*`, `JAMF_*`, `INTUNE_*` | Injected by `passkey run <profile>`; unchanged. |

## Sources

- Operator direction, 2026-08-31: "all i want is my claude skills workflow available to others without them having to setup a developer environment... it should be like claude but with all my skills and mcp tools attached already," plus follow-up answers (local-network audience, all MCP tools, general chat UI, no access control).
- The operator's own `~/.claude.json` (13 MCP servers) and `docs/.claude/skills/*`/`~/.claude/skills/*` SKILL.md files (read live to determine what "all my skills" safely means — see "Known Gaps").
- `claude_agent_sdk` installed package source (`types.py`, `query.py`, `__init__.py`) — read directly to confirm `resume`/`setting_sources`/`skills`/`tool`/`create_sdk_mcp_server` semantics, since this pivot's design depends on exact SDK behavior that live-testing then partially contradicted (see "Known Gaps").
- Prior `backend.md` (2026-08-29/30 record, preserved below for history).

## Assumptions

- "All my skills" was interpreted as *this repo's own two implemented capabilities* (device lookup via MCP, asset reporting via `asset_ops.py`), not literally every personal Claude Code skill on the operator's laptop — see `chat.py`'s docstring and "Known Gaps" for the specific, live-discovered reason (destructive Jamf write, personal-workspace-only paths that do not exist on this host). Flagged loudly to the operator before implementation; not overridden.
- `setting_sources=["project"]` is safe today because this repo has no `.claude/settings.json`/`CLAUDE.md` (verified) — if one is ever added, re-check that it does not unexpectedly change chat behavior.
- The 12-turn history cap and full-transcript context-stuffing is an MVP-level choice, not a production memory architecture — no summarization, no token-budget-aware truncation.

## Open Questions

1. **First-lookup (and now every-lookup) latency is unaddressed.** The old cache mitigated repeats; this pivot has no cache at all. Worth a follow-up decision on whether/how to cache general chat turns.
2. **LAN reachability is not built** — see "Known Gaps." This needs a `@devops.eng`/`deploy.md` pass (host bind, CORS or reverse proxy, and a real look at "no access control" once other machines can reach it).
3. Whether to widen the tool surface to include the operator's personal `docs/.claude/skills/*` (with or without the destructive Jamf-replace script specifically excluded) is an explicit operator decision, not resolved here.
4. Conversation memory has no eviction/summarization strategy beyond a flat 12-turn cap — revisit if real usage produces long threads that lose useful early context.

## Audit

- **Timestamp:** 2026-08-31
- **Persona id:** `backend-eng` (pivot; superseding the 2026-08-29/30 mode-router build below)
- **Actions:** operator-directed product pivot ("like Claude, all skills/MCP attached, no dev-environment setup"), `develop-be`, `document-backend`
- **Resolved runtime:** `AAMAD_TARGET_RUNTIME=claude-agent-sdk` (unchanged)
- **What was done:** deleted `preprocessor.py`/`mcp_config.py`/`device_lookup.py` and their tests; added `chat.py` (general session, full MCP parity via `CLAUDE_CONFIG_PATH`, `build_asset_report` custom tool, history-stuffing); reworked `runs.py` (`thread_id`, `RunStore` history instead of `mode`/`skill_id`/`intent_id`); rewrote `api.py` (dropped the validation-gate/mode dispatch, added `thread_id` threading); added `test_chat.py`/`test_runs.py`/`test_api.py`; ran `uv run pytest` (22 passed); live-tested against the real running host (general chat, real `nick.sanchez` lookup, two-turn memory) — see "Live Smoke Test."
- **Runtime library versions:** unchanged from the prior pass (`claude-agent-sdk`, `starlette`, `uvicorn`, `python-multipart`, `pandas`, `pyyaml`, `requests`, `pytest`) — no new dependency added.
- **Prompt Trace:** `CHAT_SYSTEM_PROMPT` constant in `chat.py`; live user prompts used in testing: "hey, what can you help me with?", "look up nick.sanchez", and a two-turn name/tool-preference exchange (see "Live Smoke Test") — no separate trace log persisted.
- **Security:** no secret values written to any tracked file; `~/.claude.json` is read (not copied) directly from the operator's home directory at runtime, so no credentials were duplicated into this repo (unlike the old `mcp.stdio.json` copy step); real employee/device data returned during the `nick.sanchez` live test was not persisted anywhere and is not reproduced in this document beyond field names.

### Follow-up Audit — same day, live activity feed

- **Timestamp:** 2026-08-31 (later same day)
- **Persona id:** `backend-eng`
- **Actions:** operator feedback ("it's static while looking up... with claude, at least you can see it thinking"), `develop-be`, `document-backend`
- **What was done:** added `Run.activity`/`RunStore.append_activity` (`runs.py`); added `on_progress` callback to `run_chat_turn` plus `_friendly_tool_name`/`_describe_tool_use`/`_describe_tool_result` helpers, replacing the old duck-typed `getattr(..., "text", None)` loop with `isinstance` checks against `AssistantMessage`/`UserMessage`/`ToolUseBlock`/`ToolResultBlock`/`TextBlock` (`chat.py`); wired the callback in `api.py`'s `_process_chat_turn`, seeding `"Connecting to the session..."` on the `running` transition; added 9 unit tests (`uv run pytest -q` → 31 passed); live-tested against the running host with a real `nick.sanchez` lookup, confirming the feed narrates tool calls (`servicenow -> snow_lookup_user_profile`, `jamf -> jamf_get_user_devices`, `intune -> intune_lookup_users`, run in parallel) and results in real time — see "Live Activity Feed."
- **No new dependency, no API route change** — `activity` is an additive field on the existing `GET /runs/{id}` response.
- **Security:** activity lines are short, human-authored descriptions of tool *names* only (never tool inputs/outputs), so no vendor data (ServiceNow/Jamf/Intune records) is echoed into the progress feed — only the final `result.text` carries retrieved data, unchanged from before.

---

*The 2026-08-29/30 mode-router record (device_lookup + asset_ops preprocessor split) that this document superseded has been removed from this file to keep it navigable; recover it from git history (`git log -p -- project-context/2.build/backend.md`) if needed for the full prior implementation detail (MCP tool-naming fix, `strict_mcp_config` fix, `max_turns` tuning, the original live smoke test against `mcp.stdio.json`).*
