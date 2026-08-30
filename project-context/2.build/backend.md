# Fleet Recon Backend Implementation — Session Host (supersedes the CrewAI record below)

**This document supersedes the previous `backend.md`** (CrewAI Application Crew + FastAPI enterprise scaffold in `backend/`). That tree is leftover, unused, and must not be treated as the product — see `project-context/1.define/architecture-fork.md` and `project-context/2.build/setup.md`. The Fleet Recon MVP backend **is** the session host in `session-host/fleet_session_host/`: a preprocessor, a host script runner that wraps the existing `passkey`-invoked asset-ops scripts, and a Claude Agent SDK session for one-identifier lookups over local stdio MCP. There is no CrewAI kickoff, no Postgres, no Redis, no OIDC, and no admin console in this MVP.

Runtime: `AAMAD_TARGET_RUNTIME=claude-agent-sdk` (from `aamad.config.yml`; process env was unset). Adapter: `.cursor/rules/adapter-claude-agent-sdk.mdc`.

## Scope

Implemented `lookup-user-devices` end to end on this machine (local `passkey` profiles + local Claude Code stdio MCP config), per SAD §1–§2/§6.4, PRD FR-1/FR-2/FR-3/FR-10/US-8, and `sfs/lookup-user-devices.md`:

- Deterministic preprocessor: instruction-stopword stripping, sanitize/dedupe, skill bind (`device_lookup` vs `asset_ops`), persisted `intent_id`/`skill_id`/`mode`/`input_count` with no mid-run route change.
- `asset_ops`: host writes a temp username CSV (or passes through an uploaded CSV as-is), then subprocesses `asset_report_build.py` (passkey `servicenow`) and `asset_report_mdm.py` (passkey `jamf_api` + `intune`) with a **fixed argv** — never a shell string built from chat text, never unconstrained Bash. Emits `chat.csv_preview`.
- `device_lookup`: Claude Agent SDK session with `allowed_tools` locked to the `device-lookup` skill's three tools, enforced a second time by a `PreToolUse` hook. Loads `MCP_SERVERS_CONFIG` (stdio only); returns a Diagnostic instead of a fabricated lookup when the operator hasn't filled in the real MCP command/args yet.
- Thin private HTTP API on `127.0.0.1:8100` for the future Vite proxy (not wired by this persona).
- 25 passing unit tests with no live vendor calls (mocked subprocess / no-SDK-import diagnostic paths).
- **Live-smoke validated on this machine, both paths** (see "Live Smoke Test" below) — `asset_ops` ran against real ServiceNow + Jamf + Intune via the operator's `passkey` profiles, and `device_lookup` ran a real Claude Agent SDK session over local stdio MCP against the same real vendors, once the operator supplied real `mcp.stdio.json` values and a real LiteLLM key. Two real bugs surfaced only by this live `device_lookup` run (never reachable by mocked/diagnostic-path tests) were found and fixed — see "Live Smoke Test" and "Known Gaps".

## How to Run

```bash
# From repository root
cp .env.example .env
# Fill ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY / LITELLM_MODEL for device_lookup.
# asset_ops needs no LiteLLM config -- only `passkey` on PATH with servicenow/jamf_api/intune profiles.

cd session-host
uv sync
uv run python -m fleet_session_host
# Listens on 127.0.0.1:8100 (SESSION_HOST_HOST / SESSION_HOST_PORT)
```

Pip fallback: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m fleet_session_host`.

Tests:

```bash
cd session-host
uv run pytest -q
# 25 passed
```

## Package Layout

```text
session-host/fleet_session_host/
  __main__.py       # uv run / python -m entrypoint; runs uvicorn on SESSION_HOST_HOST:PORT
  settings.py        # env loading (.env.example names only), skeleton/readiness checks
  preprocessor.py     # stopword stripping, sanitize/dedupe, skill bind (device_lookup vs asset_ops)
  asset_ops.py         # temp CSV writer, fixed-argv passkey subprocess runner, partial-failure handling
  csv_preview.py         # chat.csv_preview builder: fixed 12-column header, 10-row cap, truncated flag
  mcp_config.py          # loads MCP_SERVERS_CONFIG, detects <OPERATOR_SUPPLY> placeholders
  device_lookup.py       # Claude Agent SDK session, locked allowed_tools, PreToolUse hook, vuln short-circuit
  runs.py                 # in-memory QueryRun record + thread-safe store (session-file retention, no DB)
  api.py                   # Starlette app: /api/v1/health, /ready, /runs, /runs/{id}
session-host/tests/         # 25 unit tests, no live vendors
```

`backend/` (FastAPI + CrewAI) is untouched and unused. `session-host/pyproject.toml` gained `starlette`, `uvicorn`, and `python-multipart` as **explicit** direct dependencies (they were already transitively resolved by `claude-agent-sdk` — no new external dependency surface was introduced; this only makes the pin durable across SDK upgrades). `uv.lock` was re-resolved (`uv lock`) after the change; no other package versions moved.

## Skill Bind (Preprocessor)

Pure host code, no MCP/script calls (`preprocessor.py`):

1. Tokenize raw text on identifier-shaped chunks (letters/digits/`.`/`_`/`-`/`%`/`+`/`@`).
2. Drop any token that case-insensitively matches the instruction-stopword set (`look`, `up`, `these`, `users`, `devices`, `serial`, `hostname`, `username`, `please`, `for`, `the`, ... — see `STOPWORDS` in `preprocessor.py`). This is a heuristic list, not an exhaustive NLP model; see Open Questions.
3. Canonicalize survivors (casefold, drop email domain) and dedupe, preserving first-seen order.
4. Bind:
   - Any CSV upload (any row count) → `asset_ops`, regardless of accompanying text.
   - Exactly one surviving identity, no CSV → `device_lookup`.
   - Two or more surviving identities, no CSV → `asset_ops`.
   - Zero surviving identities, no CSV → rejected (`VALIDATION_ERROR`, no connector/script call).
5. `mode`, `skill_id` (`lookup-user-devices`), `intent_id` (`asset-ops` / `device-lookup`), and `input_count` are set once at run creation and never mutated.

`MICRO_QUERY_MAX_SUBJECTS = 4` is **not implemented** here on purpose — it is not used to choose MCP vs scripts for a name list (SAD §1.2/§2.5).

## `asset_ops` (Host Script Runner)

`asset_ops.py::run_asset_ops`:

1. Refuse to run if `passkey` is not on `PATH` (`shutil.which`) — returns a Diagnostic naming the required profiles (`servicenow`, `jamf_api`, `intune`) instead of shelling out to anything.
2. Write the identity list to `SESSION_TMP_DIR/<run_id>-usernames.csv` (header `Usernames`), or pass an uploaded CSV through unchanged to `SESSION_TMP_DIR/<run_id>-upload.csv` (the scripts already handle `Usernames`/`Username`/`Email`/`User Email` and strip domains).
3. Step 1 — fixed argv, no shell string:
   ```
   passkey run servicenow -- <session-host-python> asset_report_build.py \
     --location <tmp-csv> --output <SESSION_REPORTS_DIR>/devices-<run_id>.csv --platforms macOS,Windows
   ```
4. Step 2 — fixed argv:
   ```
   passkey run jamf_api -- passkey run intune -- <session-host-python> asset_report_mdm.py \
     --location <SESSION_REPORTS_DIR>/devices-<run_id>.csv
   ```
5. `<session-host-python>` is `sys.executable` (the session host's own `uv`-managed interpreter, which already has `pandas`/`pyyaml`/`requests`) — not a second venv. Scripts are invoked by absolute path so `fleet_common` imports resolve regardless of subprocess `cwd`.
6. Reads the result CSV with `pandas`, reindexes to the fixed 12-column header, and returns `chat.csv_preview`. If step 1 produces no file, the run is `failed`. If step 1 succeeds but step 2 fails, the run is `partial` and **still returns the step-1 CSV** (missing MDM columns render as `""`) — a failed source is a result state, not a crash (SAD §2.7).
7. The model never sees the identity list or the CSV body — only the capped `stdout`/`stderr` tail from each step (`step1_summary` / `step2_summary`), and only for future/optional model narration; the HTTP API today does not forward these to a model at all (no model call happens on the `asset_ops` path).

`--platforms "macOS,Windows"` is always passed for this skill, matching the task instruction ("use `--platforms` when the user asked for devices") and `docs/.claude/skills/asset-ops/SKILL.md`'s guidance for a computer-only device list.

## `device_lookup` (Claude Agent SDK)

`device_lookup.py::run_device_lookup`, only reached when the preprocessor bound exactly one identity and no CSV:

1. If the phrasing matches vulnerability-assessment keywords (`vuln`, `cve`, `exposure`, `tenable`, ...), return a Diagnostic immediately — Tenable is explicitly **not** part of this skill's MVP tool set or MCP config (`docs/.claude/skills/device-lookup/SKILL.md` scopes it to vuln phrasing, but no Tenable server is configured for Fleet Recon; see "Do not build" in the task and setup.md's server list). This never imports the SDK.
2. Load `MCP_SERVERS_CONFIG` (`mcp_config.py`). If the file is missing, malformed, missing a required server, or still has `<OPERATOR_SUPPLY>` placeholders, return a Diagnostic naming exactly what's missing. `asset_ops` is entirely unaffected by this check.
3. If `ANTHROPIC_BASE_URL` / `LITELLM_MODEL` are unset, return a Diagnostic (no raw Anthropic fallback — LiteLLM only, per setup.md).
4. Otherwise build `ClaudeAgentOptions`:
   - `allowed_tools = ["mcp__jamf__jamf_get_device_summary", "mcp__intune__intune_lookup_device", "mcp__servicenow__snow_lookup_user_profile"]`. **Confirmed live**: the Claude Code CLI always registers MCP tools as `mcp__<server>__<tool>` (server name = the key in `mcp_servers`/`mcp.stdio.json`, i.e. `jamf`/`intune`/`servicenow`) — the bare name from `docs/.claude/skills/device-lookup/SKILL.md` is never callable. This was originally implemented with the bare names (matching the SKILL.md doc literally) and confirmed **broken** by a live run: the model correctly called `mcp__jamf__jamf_get_device_summary`, and the `PreToolUse` hook denied it because the bare-name allowlist never matched, burning all turns on denials before the run failed on `max_turns`. Fixed in both `ALLOWED_TOOLS` and the hook's allowlist.
   - `disallowed_tools` includes `Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep`, `WebFetch`, `WebSearch`.
   - `strict_mcp_config=True`, `setting_sources=[]`. **Added after a live finding**: without these, the bundled Claude Code CLI subprocess also auto-discovers the operator's own `~/.claude.json` (all `user`/`project` settings sources, plus every other locally-registered MCP server — in this operator's case 10 additional servers: `atlassian`, `slack`, `calendar`, `drive`, `gmail`, `people`, `docs`, `sheets`, `slides`, `tenable`) and merges them in alongside the 3 servers passed programmatically. The model saw a much larger tool surface than intended and burned turns exploring it via the CLI's built-in `ToolSearch` tool, even though `PreToolUse` would still have denied any call outside the allowlist. `strict_mcp_config` restricts the session to exactly the `mcp_servers` passed in; `setting_sources=[]` stops the CLI from loading the operator's personal settings at all.
   - `hooks={"PreToolUse": [...]}` — a second, independent enforcement layer that denies any tool call whose name is not in the allowlist, with a `permissionDecisionReason`. This is defense in depth on top of `allowed_tools`/`disallowed_tools`.
   - `mcp_servers` built only from non-placeholder entries in `MCP_SERVERS_CONFIG` (`type: stdio`, `command`, `args`, `env` verbatim from the operator's file — nothing invented).
   - `model=LITELLM_MODEL`, `env={"ANTHROPIC_BASE_URL": ..., "ANTHROPIC_API_KEY": ...}`.
   - `max_turns=10` (raised from an initial `6` after live testing: even with the tool-name fix, the model reliably spends 1-2 turns on a denied `ToolSearch` attempt and occasionally retries a tool call with the wrong argument name — e.g. `serial` vs. the real `serial_number` — before succeeding. A single-device serial lookup was observed completing at exactly `num_turns=6`, leaving zero margin for a username that fans out to ServiceNow + Jamf/Intune).
5. Runs `claude_agent_sdk.query(...)`, collects assistant text blocks, and returns a `chat.device_card` (conversational summary), never a CSV.

`claude_agent_sdk` is imported **lazily inside the function**, not at module import time, so the rest of the host (and its tests) never depend on the SDK being importable, and the placeholder-config Diagnostic path never triggers a model call.

**This path was live-smoke-tested** on this machine (see "Live Smoke Test" below) once the operator supplied real `mcp.stdio.json` values (copied from `~/.claude.json`) and a real LiteLLM key/base URL/model. Both a bare-serial identifier and a multi-device username identifier completed successfully end to end against real Jamf/Intune/ServiceNow, after the two fixes above.

## `chat.csv_preview` Contract

`csv_preview.py` builds the exact SAD §2.6 / PRD FR-10 payload for every `asset_ops` run, 4 names or 50:

```json
{
  "type": "chat.csv_preview",
  "filename": "devices-<run_id>.csv",
  "headers": ["Username", "Serial", "Platform", "State", "Substate", "Model", "Asset Tag", "Notes", "MDM", "MDM Status", "MDM Last Check-In", "MDM Detail"],
  "preview_rows": [ { "Username": "...", "...": "..." } ],
  "row_count": 0,
  "truncated": false,
  "file_ref": "devices-<run_id>.csv"
}
```

`preview_rows` is a list of **objects** keyed by header name (the spec's JSON example left the row shape implicit — see Assumptions). Capped at 10 data rows; `row_count` is the true row count from the file; `truncated = row_count > 10`. Any of the 12 fixed columns missing from the on-disk CSV (e.g. the MDM step failed) is padded with `""` rather than changing the payload shape per run.

## HTTP API (Minimum, Same-Origin, Private Bind Only)

Binds to `SESSION_HOST_HOST:SESSION_HOST_PORT` (default `127.0.0.1:8100`). No CORS middleware. No admin routes, no action-confirm, no canvas, no OIDC. Not an open proxy — every route either runs the deterministic preprocessor or reads back an already-computed run record; nothing here forwards arbitrary input to MCP or `passkey`.

| Method & path | Body | Behavior |
| --- | --- | --- |
| `GET /api/v1/health` | — | `{"status": "ok"}` liveness. |
| `GET /api/v1/ready` | — | `{"status": "ok"\|"degraded", "problems": [...]}` — checks `ASSET_OPS_SCRIPTS_DIR` exists, `MCP_TRANSPORT=stdio`, and `passkey` is on `PATH`. |
| `POST /api/v1/runs` | `application/json {"text": "..."}` **or** `multipart/form-data` with a `file` field (CSV) | Runs the preprocessor; `400 VALIDATION_ERROR` on zero identities; otherwise `202` with the run summary and kicks off `asset_ops`/`device_lookup` as an asyncio background task. |
| `GET /api/v1/runs/{run_id}` | — | Run summary; `result` is the `chat.csv_preview` or `chat.device_card` object once terminal, else `null`. `404` for an unknown id. |

Run summary shape: `id`, `correlation_id`, `skill_id`, `intent_id`, `mode`, `input_kind`, `input_count`, `status` (`queued`/`running`/`partial`/`completed`/`failed`), `created_at`, `updated_at`, `result`, `error`, `diagnostic`. No SSE/WebSocket in this MVP — the client polls `GET /runs/{id}` (this is a deliberate minimum-scope choice; see Open Questions).

## Live Smoke Test (Ran on This Machine 2026-08-29 and 2026-08-30)

This machine has real `passkey` (`servicenow`/`jamf_api`/`intune`) profiles and a real `passkey` binary on `PATH`, so the `asset_ops` path was smoke-tested against **live** ServiceNow/Jamf/Intune, not just mocked subprocess calls:

```bash
cd session-host && uv sync
uv run python -m fleet_session_host &          # background, port 8100
curl -s -X POST http://127.0.0.1:8100/api/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{"text":"look up these users devices\n<username1>\n<username2>\n<username3>\n<username4>"}'
# -> 202 {"mode":"asset_ops","input_count":4,...}
curl -s http://127.0.0.1:8100/api/v1/runs/<id>
# -> status "completed", chat.csv_preview with real Not-Found-in-SN and a real Intune-managed
#    Windows device (serial, model, asset tag, last check-in) returned through the actual
#    asset_report_build.py -> asset_report_mdm.py pipeline
```

Also verified: `POST /api/v1/runs` with a CSV upload (`multipart/form-data`, `Username` header, 1 row) completed the same pipeline end to end; a 4-identity name-list run and a 10-identity name-list run (real, randomly-sampled active ServiceNow usernames) both bound `asset_ops` correctly and completed with real per-device Jamf/Intune enrichment, including a `truncated: true` result once row count exceeded the 10-row preview cap; `GET /api/v1/health` and `/ready` responded correctly.

**`device_lookup` round (2026-08-30), once the operator supplied real config:** `session-host/config/mcp.stdio.json` was filled in with the real `jamf`/`intune`/`servicenow` stdio `command`/`args`/`env` copied verbatim from the operator's own Claude Code config (`~/.claude.json`, which already had these three servers fully configured with real credentials), and `.env` was filled in with a real `ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL`/`LITELLM_MODEL`. The first live run (a single macOS serial) failed with `Reached maximum number of turns (6)`; a debug transcript capture (`sdk.query()` message-by-message) showed the real root causes documented in "Known Gaps" below. After both code fixes:

- A single macOS serial (`snow`-free path) completed successfully — real Jamf data (model, OS version, last check-in, compliance detail, assigned user) rendered as a `chat.device_card` summary.
- A username with three assigned devices (ServiceNow department/manager/last-login profile, one primary Jamf device with compliance detail, correctly not fanning out to the other two ServiceNow-listed assets) also completed successfully in a single conversational summary — confirming the skill's "one identifier, primary device only" scope holds even when ServiceNow reports multiple assets.

Real output (usernames, serials, asset tags, device compliance detail) is **not reproduced in this document** — it is live employee/device data from the operator's ServiceNow/Jamf/Intune tenants. The temp/report CSVs this smoke test wrote under `session-host/var/tmp/` and `session-host/var/reports/` were deleted after verification (both directories are git-ignored by `.gitignore` lines 35–38 regardless); `session-host/config/mcp.stdio.json` itself is also git-ignored, so the real credentials copied into it are not committed.

## Env Table

Names only, from `.env.example` (already present; none added or renamed):

| Name | Used by |
| --- | --- |
| `AAMAD_TARGET_RUNTIME` | Resolved runtime marker (`claude-agent-sdk`). |
| `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `LITELLM_MODEL` | `device_lookup.py` → `ClaudeAgentOptions` (LiteLLM Anthropic-compatible proxy; never a raw Anthropic key). |
| `SESSION_HOST_HOST`, `SESSION_HOST_PORT` | `__main__.py` → uvicorn bind (default `127.0.0.1:8100`). |
| `ASSET_OPS_SCRIPTS_DIR` | `asset_ops.py` → absolute paths to `asset_report_build.py` / `asset_report_mdm.py`. |
| `SESSION_TMP_DIR` | `asset_ops.py` → temp username/upload CSVs. |
| `SESSION_REPORTS_DIR` | `asset_ops.py` / `csv_preview.py` → result CSVs backing `chat.csv_preview`. |
| `MCP_TRANSPORT` | Must be `stdio`; `settings.check_skeleton()` flags anything else. |
| `MCP_SERVERS_CONFIG` | `mcp_config.py` → operator-filled `session-host/config/mcp.stdio.json`. |
| `SNOW_HOST`, `SNOW_USERNAME`, `SNOW_PASSWORD` | Injected by `passkey run servicenow`; the session host never reads these directly. |
| `JAMF_BASE_URL`, `JAMF_CLIENT_ID`, `JAMF_CLIENT_SECRET` | Injected by `passkey run jamf_api`. |
| `INTUNE_TENANT_ID`, `INTUNE_CLIENT_ID`, `INTUNE_CLIENT_SECRET` | Injected by `passkey run intune`. |

No `DATABASE_URL`, `REDIS_URL`, `OIDC_*`, `CREWAI_*`, or MCP HTTP URL was added — none of those exist in `.env.example` and none were invented here.

## Tests

`session-host/tests/` — 25 tests, `uv run pytest -q` → `25 passed`, no live vendor calls:

- `test_preprocessor.py`: the example request (4 names + "look up these users devices") binds `asset_ops`, `input_count=4`; a single serial/username with no list binds `device_lookup`; any CSV binds `asset_ops` even with accompanying single-name text; zero identities is rejected before any connector call; emails dedupe against bare usernames; 50 names use the same route as 4; vuln-phrasing detection.
- `test_asset_ops.py`: fixed argv for both passkey steps (`subprocess.run` mocked); the identity list never appears on any argv or in the model-facing stdout summary (only in the temp CSV file); missing `passkey` returns a Diagnostic **without calling `subprocess.run` at all**; a step-2 failure still returns `partial` with the step-1 rows; CSV upload is passed through byte-for-byte and `input_count` dedupes by email domain; missing scripts directory returns a Diagnostic.
- `test_csv_preview.py`: exact 12-column header and `chat.csv_preview` schema; 10-row preview cap and `truncated` flag on 15 rows; missing MDM columns padded to `""`; exactly 10 rows is not truncated.
- `test_device_lookup.py`: vulnerability phrasing short-circuits before any MCP/SDK involvement; missing `MCP_SERVERS_CONFIG` and placeholder `<OPERATOR_SUPPLY>` config both return a clear Diagnostic; `ALLOWED_TOOLS` matches `device-lookup/SKILL.md` exactly.
- `test_mcp_config.py`: missing file, the real example placeholder file, and a fully filled-in config are classified correctly.

`docs/.claude/skills/asset-ops/scripts/tests/*` (the skill pack's own script tests) were not touched and were not run as part of this change — they test the scripts directly, not the host wrapper.

## Known Gaps

- **[Fixed, found live 2026-08-30] MCP tool naming.** `docs/.claude/skills/device-lookup/SKILL.md` names the three tools with bare names (`jamf_get_device_summary`, `intune_lookup_device`, `snow_lookup_user_profile`). The Claude Code CLI actually registers MCP tools as `mcp__<server>__<tool>`. `ALLOWED_TOOLS` and the `PreToolUse` hook were built against the bare names and consequently **denied the real tool call every time** — confirmed via a live debug-transcript capture showing the model calling `mcp__jamf__jamf_get_device_summary` and the hook rejecting it as "not in the allowlist". Fixed by using the prefixed names throughout `device_lookup.py`; `test_device_lookup.py::test_allowed_tools_matches_device_lookup_skill` updated to match.
- **[Fixed, found live 2026-08-30] Unintended MCP/settings leakage.** `ClaudeAgentOptions` defaults (`strict_mcp_config=False`, `setting_sources=None` → CLI default `["user","project"]`) let the bundled Claude Code CLI merge in the operator's entire personal `~/.claude.json` (10+ other MCP servers) on top of the 3 servers passed programmatically, directly contradicting this module's stated design ("the model cannot expand its own tool access"). Fixed by setting `strict_mcp_config=True` and `setting_sources=[]`.
- Even after both fixes, a single-device serial lookup completed in exactly `num_turns=6` (the model spends 1-2 turns on a denied `ToolSearch` exploration attempt, plus occasional tool-argument-name retries, before calling the right tool correctly) — `max_turns` was raised to `10` to give headroom for a multi-device username; this is an observed behavior of the current model/CLI combination, not a hard guarantee, and should be re-checked if the model or CLI version changes.
- Asset-ops optional step 1.5 (ServiceNow-gap MCP fill via `jamf_get_user_devices`/`intune_lookup_users`) is **not implemented** — it is optional and not the default for this skill (SAD §2.1/§2.8); flagged here rather than built.
- `asset_report_app.py` (app health), `jamf_group_sync.py` (write), Cortex, and Tenable are intentionally not wired into this skill, per the task's "Do not build" list.
- No SSE/WebSocket progress stream; clients poll `GET /runs/{id}`. Acceptable for this MVP's minimum-API scope, but means "first progress within 10s" (SAD §2.7) is only observable via polling cadence, not a push event.
- Session/run records are process-memory only; a host restart loses in-flight run status (matches "session files are the retention" — SAD §2.4).
- No automated test drives the Starlette HTTP layer end to end (`api.py`); it was verified manually (see Live Smoke Test) rather than via an automated integration test, to avoid adding `httpx`/`TestClient` as an undeclared test dependency. `starlette`/`uvicorn`/`python-multipart` were added as **explicit** dependencies; a future QA pass could add `httpx` as a declared dev dependency for real endpoint tests.
- No rate limiting, no per-actor auth beyond the private bind — matches "not an open proxy" but is not a full authorization model (Future Work per SAD §8.2).

## Sources

- `project-context/2.build/setup.md` (folder layout, env names, ports, handoff — authoritative for conflicts on folders/env/ports)
- `project-context/1.define/sad.md` §1–§2, §6.4, Implementation Guidance
- `project-context/1.define/architecture-fork.md` §6–§7
- `project-context/1.define/prd.md` FR-1, FR-2, FR-3, FR-10, US-8
- `project-context/1.define/sfs/lookup-user-devices.md`
- `docs/.claude/skills/asset-ops/SKILL.md`
- `docs/.claude/skills/device-lookup/SKILL.md`
- `aamad.config.yml`, `.cursor/rules/adapter-claude-agent-sdk.mdc`
- `.env.example`, `session-host/config/mcp.stdio.example.json`
- Live `passkey`/ServiceNow/Jamf/Intune smoke test on this machine, 2026-08-29 (`asset_ops`) and 2026-08-30 (`device_lookup`, see above)

## Assumptions

- No conflicts arose between `setup.md` and the SAD/PRD/SFS — `setup.md`'s folder layout, env names, and port (`8100`) match the SAD/PRD's session-host description exactly, so no "setup.md wins" override was needed.
- `chat.csv_preview.preview_rows` is a list of objects keyed by header name (the SAD/PRD JSON examples left this implicit — only `[]` was shown). A future frontend consumer should treat this as the contract unless the operator specifies list-of-lists instead.
- `filename`/`file_ref` use `devices-<run_id>.csv` (no separate "session id" concept exists yet — one HTTP request is one run is one session, consistent with the SAD's own open question about session/run identity).
- The instruction-stopword list in `preprocessor.py` is a pragmatic heuristic tuned to the example request and this skill's phrasing, not a general NLP intent classifier; it is expected to need iteration as real phrasing is observed (flagged for `@qa.eng`).
- `sys.executable` (the session host's own interpreter) is sufficient to run the asset-ops scripts because they only need `pandas`/`requests`/stdlib, which are already session-host dependencies; the scripts' own docs assume a separate `~/work/.venv`, which does not exist in this repository layout and was not recreated.
- ~~`device_lookup`'s exact MCP tool naming... remains unconfirmed~~ — **resolved 2026-08-30**: confirmed live to be `mcp__<server>__<tool>`-prefixed; see Known Gaps.
- Adding `starlette`, `uvicorn`, and `python-multipart` as explicit `session-host/pyproject.toml` dependencies (previously only transitive via `claude-agent-sdk`) is within `@backend.eng`'s scope (implementing the HTTP API) and does not violate "no FastAPI/CrewAI adapters" — these are a generic ASGI stack, not a reimplementation of SN/Jamf/Intune.

## Open Questions

1. ~~**Live MCP stdio config**~~ — **resolved 2026-08-30**: `session-host/config/mcp.stdio.json` now has real `command`/`args`/`env` for `jamf`, `intune`, `servicenow`, copied from the operator's `~/.claude.json`.
2. ~~**LiteLLM gateway values**~~ — **resolved 2026-08-30**: the operator supplied a real `ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL`/`LITELLM_MODEL` in `.env`.
3. ~~Exact MCP tool naming convention~~ — **resolved 2026-08-30**: confirmed `mcp__<server>__<tool>`-prefixed; see Known Gaps.
4. Whether asset-ops optional step 1.5 (ServiceNow-gap MCP fill) should be added to this skill's default path, or stays operator-invoked only (SAD/PRD leave this open).
5. Session/run retention and multi-user isolation on a shared host — still open at the SAD level; this implementation keeps records in a single process's memory with no eviction policy.
6. Whether a future iteration should add an SSE/WebSocket progress stream, given SAD §2.7's "first progress within 10 seconds" target is easier to demonstrate with push events than polling.
7. `max_turns=10` for `device_lookup` is an empirically-chosen number based on a handful of live runs on one model/CLI version, not a formal budget derived from the SKILL.md tool matrix — worth revisiting if turn-exhaustion Diagnostics recur in practice.

## Audit

- **Timestamp:** 2026-08-29 (initial build), 2026-08-30 (device_lookup live-tested, two bugs fixed)
- **Persona id:** `backend-eng`
- **Actions:** `develop-be`, `document-backend`
- **Resolved runtime:** `AAMAD_TARGET_RUNTIME=claude-agent-sdk` (from `aamad.config.yml`)
- **Runtime library versions:** `claude-agent-sdk==0.2.148` (live-invoked 2026-08-30), `starlette==1.6.0`, `uvicorn==0.52.4`, `python-multipart==0.0.32`, `pandas==2.3.3`, `pyyaml==6.0.3`, `requests==2.34.2`, `pytest==8.4.2`
- **LiteLLM / model names (no secrets):** `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY` (LiteLLM key name only), `model=LITELLM_MODEL` — operator supplied real values in `.env` on 2026-08-30; a real model call occurred during live testing (see Live Smoke Test)
- **MCP transport:** `MCP_TRANSPORT=stdio` (only transport implemented; HTTP MCP was not built); `strict_mcp_config=True`/`setting_sources=[]` added 2026-08-30 to prevent the CLI from merging in the operator's personal MCP/settings config
- **Temperature / max_tokens:** not set explicitly (SDK/CLI defaults); `max_turns` raised from `6` to `10` on 2026-08-30 based on live turn-count observations
- **Prompt Trace:** the two `device_lookup` system prompts used in live testing are the `DEVICE_LOOKUP_SYSTEM_PROMPT` constant in `device_lookup.py` (unchanged) with user prompt = the bare identifier (`Y76N6GF94G`, then a real username) — no separate trace log was persisted; the debug transcript that surfaced the two bugs was captured to a throwaway script (`/tmp/fr_debug_device_lookup.py`) and deleted after use, not committed
- **Tool usage:** read PRD/SAD/architecture-fork/SFS/setup.md/skill packs/adapter rule/`.env.example`/`mcp.stdio.example.json`; ran `uv sync` / `uv lock` in `session-host/`; wrote `session-host/fleet_session_host/*`, `session-host/tests/*`, updated `session-host/pyproject.toml`, `session-host/requirements.txt`, `session-host/uv.lock`; ran `uv run pytest` (25 passed); ran live manual smoke tests of the running host against real `passkey`-backed ServiceNow/Jamf/Intune (both `asset_ops` and, on 2026-08-30, `device_lookup`), then deleted the resulting (git-ignored) temp/report CSVs containing real employee data; on 2026-08-30, edited `device_lookup.py` (tool names, `strict_mcp_config`/`setting_sources`, `max_turns`) in response to live findings and updated `test_device_lookup.py` accordingly (25 tests still pass)
- **Security:** no secret values written to any tracked/committed file; `session-host/config/mcp.stdio.json` was filled in with real credentials copied from the operator's own `~/.claude.json` on 2026-08-30, but that file is git-ignored (`.gitignore` lines 39-40) and was never printed in full (only key presence/length was ever checked, never values); real employee/device data produced during both live smoke tests was not committed and was deleted from `session-host/var/tmp`/`session-host/var/reports` after each verification
