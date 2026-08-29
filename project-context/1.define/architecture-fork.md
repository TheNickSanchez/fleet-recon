# Architecture comparison: session host vs enterprise workspace

## Context

This note compares (A) the 2026-08-29 system-arch revision that kept the CrewAI/FastAPI/Postgres SAD and added skill binding, a 4-name threshold, and chat CSV artifacts, with (B) the Claude suggestion to ship a thin Claude Code + MCP session host wrapping the already-working `development-test2` skills.

**Decision:** Ship (B) as MVP. Keep (A)’s functional gaps (intent table, identical CSV renderer, threshold 4) and drop (A)’s platform. The enterprise workspace (Postgres, Redis, OIDC, admin vault, canvas collaboration, CrewAI) is Future Work, not the product that makes Claude Code skills usable by non-developers.

## 1. Where the two proposals already agree (~80%)

| Topic | Both say |
| --- | --- |
| Dual-engine routing | Same mechanism as PRD FR-2. Swap `1–5` → `1–4`. Not a new invention. **Superseded after skill-pack review (§7):** a pasted **name list** always uses `asset-ops` scripts; MCP is `device-lookup` for one identifier. |
| Batch path | `asset_report_build.py` (ServiceNow identity + hardware) then `asset_report_mdm.py` (Jamf macOS, Intune Windows) is already SAD §2.2 / §2.3. Convert names to CSV and run the script so the model does not touch each row. |
| Device-lookup sources | ServiceNow + Jamf + Intune only. Not Cortex XDR or Tenable unless a different intent says so. |
| Output | Name-list runs emit the **same** normalized rows and the **same** Slack-style CSV preview + copy + download. Path must be invisible to the requestor. |
| Intake | Keep FR-1 sanitize / dedupe. Strip instruction prose so "look up these users devices" is not five fake usernames. |

The previous revision overstated the batch path as new work. Claude is correct: that pipeline was already specified.

## 2. The three functional gaps (both identified; Claude’s schema is tighter)

### 2.1 Intent → tool-subset table

The previous revision specified only `lookup-user-devices` → build + mdm. That is necessary but incomplete. Claude’s **table** is the missing contract, because the model must not improvise connectors:

| Intent (examples) | Allowed MCP / scripts | Not allowed |
| --- | --- | --- |
| Device lookup ("look up these users devices") | ServiceNow user/device + Jamf + Intune; scripts `asset_report_build` → `asset_report_mdm` | Cortex XDR, Tenable, `asset_report_app` |
| App health | Device-lookup set **plus** `asset_report_app` | Cortex XDR, Tenable unless also asked |
| Security / vuln phrasing | Device-lookup set **plus** Tenable (and Cortex only if the skill declares it) | Unrelated mutation tools |

The session host computes `allowed_tools` from this table **before** the model runs. The model does not get to add Tenable because a name “looked security-ish.”

### 2.2 CSV-in-chat render contract

The previous revision added FR-10 / `ResultArtifact` / `chat.artifact`. Claude’s name is better as the UI contract: **`chat.csv_preview`**.

```json
{
  "type": "chat.csv_preview",
  "filename": "devices-<session>-<run>.csv",
  "headers": ["username", "serial", "platform", "mdm_status"],
  "preview_rows": [],
  "row_count": 0,
  "truncated": false,
  "file_ref": "session-scoped path or blob"
}
```

Frontend: one component for both routes — inline table, Copy, Download. File backing: session-scoped temp/reports directory, same idea as existing `asset_report_html.py` / `asset_coverage.py` writes. Do not invent a second formatter per path. That identical-output rule is a **design principle**, not a CSS detail.

Object storage, Postgres artifact tables, and signed download URLs are Future Work. MVP files live on the session host disk (or an equivalent session temp) and are deleted with the session.

### 2.3 Threshold 4

Agreed. Implementation constant `MICRO_QUERY_MAX_SUBJECTS = 4`.

## 3. The real disagreement: what you are shipping

| | Previous SAD revision (A) | Claude (B) — **MVP** |
| --- | --- | --- |
| Runtime | CrewAI sequential crew | Claude Code / Claude Agent SDK session |
| Connectors | New Python adapters + credential vault | Existing MCP servers (ServiceNow, Jamf, Intune) already connected in `development-test2` |
| Pasted name list (incl. 4 names) | Host-side Python adapters; **names never in the model** | Host writes temp CSV and subprocesses `asset-ops` steps 1 then 2 (passkey scripts). Do **not** fire `device-lookup` once per name. |
| Single serial/hostname/user | (not distinguished) | `device-lookup` MCP immediately (`jamf_get_device_summary` / `intune_lookup_device` / `snow_lookup_user_profile`) |
| >4 names / CSV | Redis job + object-store CSV | Same `asset-ops` subprocess as a 4-name list; token savings come from never putting the CSV body in model context |
| Persistence | PostgreSQL evidence model | Session files + chat transcript |
| Auth | OIDC + Workspace User / Administrator | No productized vault or admin console; credentials stay in MCP server config |
| UI | Chat + live canvas + settings | Prebaked chat window; canvas/admin are not required to prove the skill |
| What “revise the SAD” means | Add skills on top of the enterprise system | Replace §1.3 / §2 / §4 with a session host |

(A) was the conservative AAMAD reading of the existing PRD. It does **not** match the stated goal: *Claude Code skills and workflows available to non-developers who just want the interface to work.* That working system is (B).

The FastAPI/React scaffold already in the repo is a prototype of an enterprise workspace. It is not the validated `development-test2` path. Treating it as the MVP keeps you building Postgres, OIDC, and a tool-registry console instead of wrapping what already looks up devices.

## 4. Where Claude is adopted as-is

- Drop CrewAI, Postgres, Redis, OIDC, and the administrator credential vault from **MVP**.
- Credentials remain in MCP server configs and `passkey` profiles, not an app-managed secret store (PRD FR-7 / FR-8 / FR-9 become Future Work).
- Single identifier: MCP tools from `device-lookup` SKILL.md, constrained by the intent table.
- Pasted name list or CSV (any count): temp CSV + existing `asset-ops` scripts (`asset_report_build.py` → `asset_report_mdm.py`), host-invoked.
- Name-list runs converge on one row shape and one `chat.csv_preview` renderer.
- Intent table is explicit, not “orchestrator classifies intent.”
- **Do not adopt Claude’s original “≤4 MCP fan-out for a name list.”** That contradicts `asset-ops` (agent reads summaries, never the CSV body) and `device-lookup` (one identifier). See §7.

## 5. Where Claude is refined (do not copy blindly)

1. **The >4 script must be host-invoked, not unconstrained Bash.** If the model is allowed general `Bash`, it can skip the CSV path or shell out arbitrarily. The session host writes the temp CSV and execs the two scripts with a fixed argv/cwd. The model may be told “batch job started / finished” and must still emit `chat.csv_preview` from the script output file.
2. **MCP still uses a locked tool list.** `device-lookup` and optional step 1.5 are acceptable only after the host sets `allowed_tools` from the intent table. Otherwise you reintroduce the original gap (Cortex/Tenable on a device lookup). A pasted name list does not get four `device-lookup` novels.
3. **Non-developers still need a chat UI.** “No separate web tiers” means no distributed API/worker/database. It does not mean no UI. The existing React chat can stay as a thin client of the session host. Live canvas, collaboration WebSockets, and admin settings are deferred.
4. **Someone still has to be allowed to use org MCP credentials.** MVP can be a private internal URL plus a shared session identity, not full OIDC. It cannot be an open unauthenticated proxy to ServiceNow/Jamf/Intune.
5. **Confirmation-gated mutations (FR-6) are not moot if any skill can write.** Read-only device lookup does not need an action console. Jamf policy / ticket skills still need an explicit confirm step if those skills are exposed. Do not silently drop that because credentials live in MCP.

## 6. What to revise (updated inventory)

**Define (this change set):** SAD §1.2–1.3, §2 (crew → session + MCP + skills), intent table, `chat.csv_preview`, runtime `claude-agent-sdk`; PRD MVP vs Future Work for FR-6–FR-9; SFS processing for MCP vs script; `aamad.config.yml` runtime.

**Build (next, not this note):** replace CrewAI kickoff with a Claude Agent SDK (or Claude Code) session; wire MCP allowlists from the intent table; host-side router (`device-lookup` MCP for one id, `asset-ops` subprocess for name lists/CSV); one CSV preview component; session-scoped reports directory. Do not implement Postgres/Redis/OIDC/tool-admin to ship the example request.

**Do not build for this example:** administrator credential vault UI, connection-health console, canvas collaboration, CrewAI YAML crew, RQ workers.

## 7. Reviewed skill pack (`docs/`, `origin/master` `af27545`)

The tree is the CPE Claude Code workspace (`docs/CLAUDE.md`), not a second app. Skills live under `docs/.claude/skills/`.

| Skill | What it actually is | Product implication |
| --- | --- | --- |
| `asset-ops` | CSV that grows rightward: step 1 SN hardware (`asset_report_build.py`) → optional 1.5 SN-gap MCP fill → step 2 MDM (`asset_report_mdm.py`) → step 3 app (`asset_report_app.py`) → optional HTML. Independent Jamf group **write**. | This is the pasted-name-list / spreadsheet path. |
| `device-lookup` | One serial/hostname/user, **no ticket**. MCP immediately: `jamf_get_device_summary`, `intune_lookup_device`, `snow_lookup_user_profile`; Tenable only for vuln phrasing. | This is the 1-identifier ad hoc path, not a 50-row CSV. |
| `vulnerability-remediation` / `ticket-workflow` | Jira + Tenable + Jamf writes, canary ≤10, human gates. | Do not auto-load for "look up these users devices". |
| `report` / `session-wrap` / `sprint-brief` | HTML report, journal, Jira sprint. | Optional later chips. |
| `jamf-api-patterns` / `jamf-script-patterns` | Shared guardrails, not user chips. | Load with write skills only. |

**Credentials:** steps 1–4 and Jamf sync use `passkey run servicenow|jamf_api|intune`, not an app vault. MCP is required for step 1.5 (`jamf_get_user_devices`, `intune_lookup_users`) and for `device-lookup`. That matches the session-host fork.

**"Look up these users devices" (paste 4 names):** do **not** fire `device-lookup` four times as four chat novels, and do **not** load Tenable. Bind `asset-ops` steps 1 then 2 (computer platforms). Host writes a small CSV even for 4 names — the skill already says the agent reads the **summary**, never the CSV body. If the user clearly has a single serial/hostname/user and no list, bind `device-lookup` instead.

**Threshold 4:** not in the skills. Scripts are size-agnostic. Default for any pasted name list is scripts. Keep 4 only as a **cap if** a later live-card MCP fan-out is added; that path must never run for >4 names. Token rule is already in the skill: never dump the CSV body into context.

**Chat CSV:** today the skill points at `input/output/asset_report.csv` and optionally HTML. Slack-style `chat.csv_preview` is still the missing product surface; columns should match step 1+2: `Username, Serial, Platform, State, Substate, Model, Asset Tag, Notes, MDM, MDM Status, MDM Last Check-In, MDM Detail`.

**Writes:** `jamf_group_sync.py` (`--mode replace` is dangerous) still needs an explicit confirm in the non-dev UI.

## Sources

- Requestor goal: Claude Code skills for non-developers (2026-08-29).
- Claude suggestion (session host, intent table, `chat.csv_preview`, drop enterprise stack).
- Prior system-arch revision: skill binding, threshold 4, FR-10 artifacts (functional; platform rejected).
- Reviewed `docs/.claude/skills/` from `origin/master` `af27545` (2026-08-29).
- [prd.md](prd.md), [sad.md](sad.md), [sfs/lookup-user-devices.md](sfs/lookup-user-devices.md).

## Assumptions

- Skill pack in `docs/.claude/skills/` is the validated CPE Claude Code workspace.
- Exact MCP names are those in the SKILL.md files (`snow_lookup_user_profile`, `jamf_get_user_devices`, `intune_lookup_users`, `intune_lookup_device`, `jamf_get_device_summary`).

## Open Questions

1. Session host process: Claude Agent SDK behind the existing Vite chat, vs embedding in Claude Code’s own UI.
2. Session file retention and multi-user isolation on a shared host.
3. Whether app-health and vuln intents ship in the same MVP or only device lookup.

## Audit

- 2026-08-29 | `system-arch` | `architecture-fork` | Compared enterprise SAD revision with Claude session-host proposal; selected session host as MVP. Resolved runtime target `claude-agent-sdk`. Prompt Trace omitted: specification, not a model invocation.
- 2026-08-29 | `system-arch` | `review-skill-pack` | Reviewed `docs/.claude/skills` at `af27545`. Split `device-lookup` (MCP, one id) vs `asset-ops` (passkey scripts, CSV). Corrected that steps 1–4 do not use MCP except 1.5.
- 2026-08-29 | `system-arch` | `align-define-artifacts` | Superseded Claude’s ≤4 MCP fan-out for name lists. SAD/PRD/SFS: lists and CSV always host-invoke `asset-ops`; MCP is `device-lookup` for one identifier.
