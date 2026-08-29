# Fleet Recon Session Host Setup

## Context

Operator decision: option B — rework setup for a Claude Agent SDK session host. The leftover FastAPI / CrewAI / Postgres tree is **not** the product. This persona writes environment, folder, and dependency skeleton only. No skill-bind, script runner, or chat UI logic.

The session host is a thin process that non-developers will later hit through the existing React chat. First workflow: **"look up these users devices"** (`lookup-user-devices`).

| Path | Engine | Connectors | Result |
| --- | --- | --- | --- |
| Pasted name list or any CSV | Host-invoked `asset_report_build.py` then `asset_report_mdm.py` | Passkey profiles `servicenow`, `jamf_api`, `intune`. MCP **none** for steps 1–4 | `chat.csv_preview` (copy + download). Agent reads script summaries, never the CSV body |
| One serial / hostname / user (no list, no CSV) | Claude Agent SDK + `device-lookup` MCP | Local stdio MCP: `jamf`, `intune`, `servicenow` | Conversational lookup card |

Optional asset-ops step 1.5 (ServiceNow gap fill) may use MCP tools `jamf_get_user_devices` and `intune_lookup_users`. It is **not** the default for this skill.

## Folder Layout

```text
/
  session-host/                         # PRODUCT skeleton (this setup)
    pyproject.toml                      # claude-agent-sdk, pandas, pyyaml, requests
    uv.lock                             # locked session-host resolve
    requirements.txt                    # pip fallback (same pins)
    .python-version                     # 3.12
    config/
      mcp.stdio.example.json            # jamf / intune / servicenow names + stdio placeholders
      mcp.http.example.json             # Future Work URL placeholders only
    var/
      tmp/                              # session-scoped temp (git-ignored contents)
      reports/                          # session-scoped report CSVs (git-ignored contents)
  docs/.claude/skills/asset-ops/scripts # HOST CWD / script location — do not copy
  docs/.claude/skills/device-lookup/    # SKILL.md for one-id MCP allowlist
  frontend/                             # existing React chat; thin client later (not this persona)
  .env.example                          # MVP env names only (no secret values)
  aamad.config.yml                      # runtime.target: claude-agent-sdk

  backend/                              # LEFTOVER — unused / to-be-replaced FastAPI + CrewAI
  tests/                                # LEFTOVER — leftover FastAPI API tests
  pyproject.toml                        # LEFTOVER — CrewAI/FastAPI deps
  uv.lock                               # LEFTOVER — leftover backend lock
  project-context/2.build/backend.md    # LEFTOVER record (CrewAI); not the ship target
```

Do not copy `docs/.claude/skills/asset-ops/scripts` into `session-host/`. Point `ASSET_OPS_SCRIPTS_DIR` at that tree. Write temp username CSVs and result files under `SESSION_TMP_DIR` and `SESSION_REPORTS_DIR` so the skill pack stays clean.

## Runtime Selection

- `aamad.config.yml` `runtime.target`: `claude-agent-sdk`
- Environment `AAMAD_TARGET_RUNTIME` was unset at setup time; resolved value is **`claude-agent-sdk`** (config file wins; prefer the env var when both are set)
- Adapter: `.cursor/rules/adapter-claude-agent-sdk.mdc`
- Model gateway: **LiteLLM** Anthropic-compatible proxy (not a raw Anthropic first-party key)

## Prerequisites

- Python 3.11–3.13 (this environment: 3.12.3). Pin file: `session-host/.python-version` → `3.12`
- `uv` (preferred) or `pip` + venv
- Operator-supplied LiteLLM key and Anthropic-compatible proxy URL (never committed)
- Operator-supplied Claude Code MCP stdio `command` / `args` for `jamf`, `intune`, `servicenow` (this workspace has no live MCP config)
- `passkey` profiles `servicenow`, `jamf_api`, `intune` on the machine that will run asset-ops steps 1–2 (name-list path)
- Existing React chat in `frontend/` is **not** wired in this persona

## Install Commands

### Session host (product)

```bash
# From repository root
cp .env.example .env
# Fill LiteLLM + passkey env names in .env. Do not commit .env.

cp session-host/config/mcp.stdio.example.json session-host/config/mcp.stdio.json
# Replace <OPERATOR_SUPPLY> command/args from the operator Claude Code MCP config.
# Do not paste secrets into the committed example file.

cd session-host
uv sync
# Fallback without uv:
# python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Resolved on 2026-08-29 (`uv sync` in `session-host/`):

| Package | Resolved version | Role |
| --- | --- | --- |
| `claude-agent-sdk` | 0.2.148 | Session coordinator (LiteLLM via `ANTHROPIC_BASE_URL`) |
| `pandas` | 2.3.3 | Already used by asset-ops scripts |
| `pyyaml` | 6.0.3 | Already used by asset-ops scripts |
| `requests` | 2.32+ (resolved 2.34.2) | Already used by asset-ops scripts |
| `pytest` | 8.4.2 | Dev extra for later unit tests |

`session-host/pyproject.toml` is `package = false` (dependency project only). No host module was added.

### Leftover FastAPI / CrewAI (unused)

```bash
# From repository root — leftover only; do not treat as the product
uv sync
uv run uvicorn backend.main:app --reload --port 8000
uv run pytest
```

This leftover process does not run asset-ops scripts, does not call MCP, and does not emit `chat.csv_preview`. Query runs stay queued. Do not add `CREWAI_*`, `DATABASE_URL`, `REDIS_URL`, or `OIDC_*` back into the MVP `.env`.

### Frontend (thin client later)

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

`frontend/.env.example` still proxies `/api` to leftover `http://127.0.0.1:8000`. `@integration.eng` retargets that at the session host after `@backend.eng` implements a listen address (`SESSION_HOST_HOST` / `SESSION_HOST_PORT`, default `127.0.0.1:8100`).

## Environment Variables

Copy `.env.example` → `.env`. Names only; values stay empty or are non-secret placeholders.

| Name | Purpose |
| --- | --- |
| `AAMAD_TARGET_RUNTIME` | `claude-agent-sdk` |
| `ANTHROPIC_API_KEY` | LiteLLM key (never a committed secret) |
| `ANTHROPIC_BASE_URL` | LiteLLM Anthropic-compatible proxy path |
| `LITELLM_MODEL` | Model id LiteLLM exposes |
| `SESSION_HOST_HOST` | Private bind address (default `127.0.0.1`) |
| `SESSION_HOST_PORT` | Host listen port (default `8100`, distinct from leftover `8000`) |
| `ASSET_OPS_SCRIPTS_DIR` | `docs/.claude/skills/asset-ops/scripts` |
| `SESSION_TMP_DIR` | Session-scoped temp (username CSV) |
| `SESSION_REPORTS_DIR` | Session-scoped report CSV for `chat.csv_preview` |
| `MCP_TRANSPORT` | Default `stdio` |
| `MCP_SERVERS_CONFIG` | Operator-filled `session-host/config/mcp.stdio.json` |
| `SNOW_HOST`, `SNOW_USERNAME`, `SNOW_PASSWORD` | Injected by passkey profile `servicenow` |
| `JAMF_BASE_URL`, `JAMF_CLIENT_ID`, `JAMF_CLIENT_SECRET` | Injected by passkey profile `jamf_api` |
| `INTUNE_TENANT_ID`, `INTUNE_CLIENT_ID`, `INTUNE_CLIENT_SECRET` | Injected by passkey profile `intune` |

Commented-out leftover names in `.env.example` (do not recreate): `DATABASE_URL`, `REDIS_URL`, `OBJECT_STORAGE_*`, `OIDC_*`, `CREWAI_*`.

Not in MVP env: Tenable / Cortex credentials, `jamf_group_sync` defaults, object-store keys.

## LiteLLM Wiring

Configure Claude Agent SDK to call LiteLLM’s Anthropic-compatible proxy. Do not send a raw Anthropic first-party key unless that is what LiteLLM is configured to accept (it is not the documented path).

1. Set `ANTHROPIC_BASE_URL` to the LiteLLM proxy Anthropic path (placeholder in `.env.example`: `https://litellm.example.invalid`).
2. Set `ANTHROPIC_API_KEY` to the LiteLLM key from the operator secret store.
3. Set `LITELLM_MODEL` to the model id LiteLLM lists (placeholder name only).
4. `@backend.eng` must pass those into `ClaudeAgentOptions` / process env (`ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `model=LITELLM_MODEL`). See adapter-claude-agent-sdk Setup.

Gateway and model names only are recorded in Audit. No secret values.

## MCP Transport Policy

| Now (this project) | Later (out of scope) |
| --- | --- |
| `MCP_TRANSPORT=stdio` | `MCP_TRANSPORT=http` |
| Local Claude Code / stdio servers | Remote HTTP MCP |
| `session-host/config/mcp.stdio.example.json` | `session-host/config/mcp.http.example.json` |
| Copy command/args from the operator Claude Code MCP config | Same server names + URL placeholders |

Server names (not secrets): **`jamf`**, **`intune`**, **`servicenow`**.

This workspace does **not** contain a live Claude Code MCP config. Example JSON uses `<OPERATOR_SUPPLY>` placeholders. Do not invent stdio packages or extra tool names beyond SKILL.md:

- `device-lookup`: `jamf_get_device_summary`, `intune_lookup_device`, `snow_lookup_user_profile` (Tenable only for vuln phrasing — not this skill)
- asset-ops optional 1.5: `jamf_get_user_devices`, `intune_lookup_users`

**Name-list / CSV path must not require MCP.** Passkey scripts cover steps 1–4. MCP is for `device_lookup` and optional step 1.5 only.

No HTTP MCP client, MCP gateway, or remote server code in this project.

## Passkey / Scripts

| Profile | Used by | Env names (values never committed) |
| --- | --- | --- |
| `servicenow` | `asset_report_build.py` (step 1) | `SNOW_HOST`, `SNOW_USERNAME`, `SNOW_PASSWORD` |
| `jamf_api` | `asset_report_mdm.py` (step 2, macOS) | `JAMF_BASE_URL`, `JAMF_CLIENT_ID`, `JAMF_CLIENT_SECRET` |
| `intune` | `asset_report_mdm.py` (step 2, Windows) | `INTUNE_TENANT_ID`, `INTUNE_CLIENT_ID`, `INTUNE_CLIENT_SECRET` |

Host cwd: `ASSET_OPS_SCRIPTS_DIR`. Fixed argv later (not this persona): `asset_report_build.py` then `asset_report_mdm.py`. Do not default-enable `asset_report_app.py` or `jamf_group_sync.py`.

Session reports stay on disk under `SESSION_REPORTS_DIR`. No object store.

## How to Run

### Session host (product — entrypoint not implemented here)

```bash
# After @backend.eng adds the host process:
#   load .env
#   cwd = ASSET_OPS_SCRIPTS_DIR (or pass that path into the runner)
#   MCP_TRANSPORT=stdio
#   Claude Agent SDK with ANTHROPIC_BASE_URL + LITELLM_MODEL
# Expected listen: 127.0.0.1:8100 (SESSION_HOST_HOST / SESSION_HOST_PORT)
```

This persona does not add a `__main__` module. A `uv run` / `python -m` command is a `@backend.eng` deliverable.

### Leftover uvicorn (not the product)

```bash
# Repository root, leftover FastAPI app
uv run uvicorn backend.main:app --reload --port 8000
```

Do not point new work at this process. Do not kick off CrewAI.

## Explicitly Not Set Up

- PostgreSQL, Redis, object storage
- OIDC / productized RBAC console
- CrewAI as the product runtime
- Credential vault UI, connection-health console, canvas collaboration
- Remote MCP HTTP servers or an HTTP MCP client
- Tenable / Cortex for this skill
- `jamf_group_sync` as a default path
- Skill-bind preprocessor, script runner, or chat UI (downstream personas)

## Next-Agent Handoff

| Agent | Next work |
| --- | --- |
| `@backend.eng` | Implement the session host (see paragraph below). Override leftover `backend.md` / CrewAI kickoff. |
| `@frontend.eng` | Skill chip **Look up users' devices**; `chat.csv_preview` card (filename, ≤10 preview rows, Copy, Download). Hide or inert canvas/admin. No backend wiring. |
| `@integration.eng` | Point `frontend` at the session host (`SESSION_HOST_PORT`). Keep same-origin / no CORS unless the host adds it. |
| `@qa.eng` | Unit: sanitization, instruction stopwords, skill bind (one id vs list/CSV). Integration: MCP fixtures / recorded payloads and script fixtures. |
| `@security.eng` | Required before Deliver (`security.require_security_assessment: true`). Host must not be an open proxy to MCP or passkey profiles. |

Backend must implement the session host per SAD §2.1/§2.5: preprocessor skill-bind, host script runner, Claude Agent SDK with LiteLLM base URL, locked allowed_tools, chat.csv_preview payload. Do not kick off CrewAI. Do not implement HTTP MCP. Override the backend persona “no external integrations” rule: wrapping existing passkey scripts + local MCP is the MVP.

## Sources

- `project-context/1.define/prd.md` (session runtime, FR-2, FR-10, US-8)
- `project-context/1.define/sad.md` §1–§2, §6.4, Implementation Guidance (SAD §4+ enterprise stack treated as Future Work)
- `project-context/1.define/architecture-fork.md` §6–§7
- `project-context/1.define/sfs/lookup-user-devices.md`
- `docs/.claude/skills/asset-ops/SKILL.md`
- `docs/.claude/skills/device-lookup/SKILL.md`
- `aamad.config.yml` (`runtime.target: claude-agent-sdk`)
- `.cursor/rules/adapter-claude-agent-sdk.mdc`
- `.cursor/agents/project-mgr.md` (`*setup-project`)
- Operator decision 2026-08-29: option B session host; LiteLLM not raw Anthropic; MCP stdio now, HTTP later (out of scope)
- LiteLLM + Claude Agent SDK tutorial (gateway env names only): `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `model`

## Assumptions

- All required spec files listed by the operator were present; no Diagnostic halt.
- Skill-pack MCP tool names in SKILL.md are authoritative until the operator supplies a live server list that differs.
- Passkey profile names `servicenow`, `jamf_api`, `intune` and the env names those scripts already read are the MVP credential surface.
- Host cwd at `docs/.claude/skills/asset-ops/scripts` is enough for `fleet_common` imports; report/temp paths are redirected via env / argv by `@backend.eng`.
- Existing `frontend/` remains the thin client; this persona does not change UI code.
- Leftover `backend/` may stay in-tree unused. Replacing or deleting it is not this persona.
- Session host bind `127.0.0.1:8100` avoids colliding with leftover uvicorn `:8000`.
- `MICRO_QUERY_MAX_SUBJECTS = 4` is not used to choose MCP vs scripts for a name list.

## Open Questions

1. **Live MCP stdio config (blocking for device-lookup and optional step 1.5).** This environment has no `~/.claude.json`, project `.mcp.json`, or `.claude/settings.json` with `mcpServers`. Operator must supply, for servers named `jamf`, `intune`, and `servicenow` only: stdio `command` and `args` copied from the existing Claude Code MCP config (no secret env values). Likely sources on the operator workstation: `~/.claude.json` `mcpServers`; a project `.mcp.json` / `.claude/settings.json` in the `development-test2` workspace; or the CPE Claude Code config referenced by `docs/CLAUDE.md` (paths such as `/Users/nick.sanchez/cpe-skills` are not in this repo).
2. Confirm live MCP tool names match SKILL.md (`jamf_get_device_summary`, `intune_lookup_device`, `snow_lookup_user_profile`, optional `jamf_get_user_devices`, `intune_lookup_users`).
3. Exact LiteLLM Anthropic-compatible URL path and the model id LiteLLM exposes (`LITELLM_MODEL`).
4. Is `passkey` on PATH in the session-host runtime, and are profile names exactly `servicenow` / `jamf_api` / `intune`?
5. Session file retention and multi-user isolation on a shared host (also open in SAD).
6. Session-host listen contract for the Vite proxy (port `8100` assumed here; leftover frontend still targets `8000`).
7. Whether app-health / vuln intents ship with device lookup (SAD / architecture-fork open question).

## Audit

- **Timestamp:** 2026-08-29
- **Persona id:** `project-mgr`
- **Actions:** `setup-project`, `install-dependencies`, `configure-env`, `document-setup`
- **Resolved runtime:** `AAMAD_TARGET_RUNTIME=claude-agent-sdk` (from `aamad.config.yml`; process env was unset)
- **Gateway / model names (no secrets):** LiteLLM Anthropic-compatible proxy via `ANTHROPIC_BASE_URL`; model id env `LITELLM_MODEL`; SDK env `ANTHROPIC_API_KEY` is the LiteLLM key name only
- **SDK / library versions recorded:** `claude-agent-sdk==0.2.148`, `pandas==2.3.3`, `pyyaml==6.0.3`, `requests==2.34.2`; installer `uv 0.12.7`; Python 3.12.3
- **Temperature / max_tokens:** N/A (no model invocation)
- **Prompt Trace:** omitted — setup artifact, not a runtime model invocation
- **Tool usage:** workspace file read of PRD/SAD/SFS/skills/adapter/config; `uv sync` in `session-host/`; writes limited to `setup.md`, `.env.example`, `.gitignore`, leftover `pyproject.toml` comment, and `session-host/` skeleton/env/dependency files
- **Security:** no secret values written; MCP example files contain placeholders only
