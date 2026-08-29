# SFS: Look up users' devices

## Context & Instructions

This System Functional Specification defines the first packaged Claude Code skill that non-developers run from the Fleet Recon chat window: **look up these users' devices**. It is derived from the PRD dual-engine routing model, the SAD capability adapters for `asset_report_build` and `asset_report_mdm`, and the requestor’s 2026-08-29 product goal.

**PRD Document**: [prd.md](../prd.md) FR-1, FR-2, FR-3, FR-7, FR-10  
**User Story / Feature ID**: US-LOOKUP-USER-DEVICES  
**Selected Runtime**: `claude-agent-sdk`

### 1. Purpose and Scope

- **Feature ID**: `lookup-user-devices`
- **Purpose**: A Workspace User pastes a natural-language request and names (or a CSV). The product binds that request to a pre-registered skill, collects device evidence from ServiceNow, Jamf Pro, and Microsoft Intune using the approved Python capabilities, and returns a spreadsheet-ready CSV in chat with a Slack-style preview and download. The user never runs Claude Code, Python, or vendor consoles.
- **In Scope**: Intent/skill binding; identity extraction distinct from instruction prose; `asset_ops` host scripts for any pasted name list or CSV (`asset_report_build` → `asset_report_mdm`); `device_lookup` MCP only for one identifier; identical CSV schema for all list sizes; chat artifact card; partial-failure columns.
- **Out of Scope**: `asset_report_app` / application-health lookup; Cortex XDR and Tenable on this skill; N× `device-lookup` for a name list; mutation/remediation (`jamf_group_sync`); unconstrained Bash; CrewAI/Postgres/OIDC/admin vault.

### 2. Traceability

- **PRD Anchors**: FR-1 Request Intake; FR-2 Skill Bind (`device_lookup` vs `asset_ops`); FR-3 Connector Collection skill-scoped to ServiceNow, Jamf, Intune; FR-10 Chat Result Artifacts; MVP AC 1–5.
- **User Story**: [us-lookup-user-devices.md](../user-stories/us-lookup-user-devices.md)
- **SAD Anchors**: §2.2 Tool Capability Model; §2.3 Script Pipeline; §2.5 Task and Turn Orchestration; §2.8 Skill Pack and Workflow Model; §3.3 Chat artifacts; §4.4 `ResultArtifact`; §6.4 Example request walkthrough.

### 3. Inputs

- **Raw chat text** (`string`, composer): Natural language plus pasted identities. Max 100,000 characters (existing `RunRequest.text` limit). May contain instruction phrases such as "look up these users devices".
- **CSV upload** (`file`, `+` menu or drag-and-drop): UTF-8 CSV with a `username` column; 5 MiB and 10,000 row limits unchanged.
- **Skill id** (`lookup-user-devices`, server-resolved): Not chosen from a developer SKILL.md at runtime. Matched from the registered workflow catalog by trigger phrases, empty-state skill chip, or explicit `intent` field.
- **Workspace context** (`workspace_id`, actor, role): Authorization and credential/tool snapshots as already specified in the SAD.
- **Optional `intent`**: Existing `RunRequest.intent` may carry a catalog skill id when the empty-state chip is used; the server still re-resolves from text and never trusts the client as the authorization source.

Identity values accepted after sanitization: usernames matching the existing pattern, plus email-shaped tokens. Instruction vocabulary and unmatched prose are not identities.

### 4. Processing Behavior

The session host decides intent and route. The model does not invent connectors.

1. Bind intent `device lookup` from phrasing or chip. Strip instruction stopwords. Sanitize identities.
2. Skill bind: **one** serial/hostname/user and no CSV → `device_lookup`. Pasted **name list** (any count, including 4) or CSV → `asset_ops`. Never run `device-lookup` once per name in a list.
3. **`asset_ops`:** host writes temp username CSV and subprocesses `asset_report_build.py` then `asset_report_mdm.py` (passkey env). MCP is not used for steps 1–4. The model reads the stdout summary, never the CSV body. Unconstrained Bash is not allowed.
4. **`device_lookup`:** set MCP `allowed_tools` from `docs/.claude/skills/device-lookup/SKILL.md`. Agent SDK calls the primary tool immediately for that one identifier. Conversational card, not a four-row CSV novel.
5. `asset_ops` writes a session report file and emits **`chat.csv_preview`** (same renderer for 4 names and 50). Canvas is not required.

Claude Code mapping (runtime is the skill pack, not Postgres):

| Claude Code path | Product object |
| --- | --- |
| `docs/.claude/skills/asset-ops/SKILL.md` | Name-list / CSV workflow `lookup-user-devices` |
| `docs/.claude/skills/device-lookup/SKILL.md` | One-identifier lookup |
| `scripts/asset_report_build.py` | Step 1 (passkey `servicenow`) |
| `scripts/asset_report_mdm.py` | Step 2 (passkey `jamf_api` / `intune`) |
| `scripts/asset_report_app.py` | Separate future workflow; not invoked by this skill |

### 5. Outputs

- **`QueryRunSummary`**: Existing fields plus `skill_id` and `artifact_id` when present.
- **SSE `chat.artifact`**: `artifact_id`, `filename`, `media_type`, `row_count`, `byte_size`, `preview_headers`, `preview_rows`, `truncated`, `download_path`, `correlation_id`.
- **CSV file**: One row per device (or one explicit no-device/not-found row per identity). Columns match asset-ops step 1+2: `Username`, `Serial`, `Platform`, `State`, `Substate`, `Model`, `Asset Tag`, `Notes`, `MDM`, `MDM Status`, `MDM Last Check-In`, `MDM Detail`. Exact extra columns follow the scripts, not free-form LLM text.
- **Chat UI**: Slack-style file card — file icon, filename (`devices-<run_short_id>.csv`), row count, header + preview table, "n more rows" if truncated, **Copy CSV**, **Copy for spreadsheet** (tab-separated), **Download**.
- **Canvas rows**: Same joined evidence; export of the filtered canvas must match artifact columns for the current filter set.
- **Partial run**: CSV still produced; `source_errors` and per-row MDM/CMDB status carry safe error categories.

### 6. Validations and Constraints

- Routing uses unique sanitized identity count, not raw token count and not instruction-word count.
- A name list of any size, including 4, is `asset_ops`. One identifier with no list is `device_lookup`.
- The name-list skill may invoke only `asset_report_build` and `asset_report_mdm`. Cortex, Tenable, `asset_report_app`, and N× `device-lookup` are not in this skill’s tool set.
- Tools must be registered, workspace-enabled, assigned to the executing worker role, and covered by a healthy-enough dependency policy (partial allowed).
- Credentials never enter chat, CSV, preview, agent context, or logs.
- Preview rows are capped; download is the full authorized artifact.
- Batch input CSV is internal and is not re-shown as the user’s download; the user receives the result CSV.
- A request never changes route mid-run; retry creates a new run.

### 7. Error Handling and Exceptions

| Condition | User-visible result | Connector/run behavior |
| --- | --- | --- |
| No skill match and no identities | Validation error; composer guidance to pick a skill or paste names | No connector calls |
| Skill match but zero identities | Ask to paste names or upload CSV; run not created | No connector calls |
| Instruction words only (e.g. "look up these users devices") | Same as zero identities | No connector calls |
| Invalid/empty after sanitization | `VALIDATION_ERROR` as today | No connector calls |
| MCP or script source fails | Run `partial`; CSV includes error/not-found columns | Other identities continue |

The report CSV is written by the host script runner (`asset_ops`) or, for one id, derived from MCP payloads (`device_lookup`). Invalid model prose is ignored. The model must not dump the CSV body into context.

### 8. Acceptance Criteria

1. "look up these users devices" plus 4 valid names → `asset_ops`, `input_count=4`, instruction words not identities, host-invoked `asset_report_build` then `asset_report_mdm`, `chat.csv_preview` in chat. No `device-lookup` MCP.
2. Same prompt plus 5 (or 50) valid names → the same `asset_ops` scripts; names and CSV body absent from the model context.
3. CSV upload → script path; download is the device report, not the upload.
4. Copy and Download work from the chat card.
5. Preview at most 10 data rows; download has all rows.
6. Workspace User never sees SKILL.md, script paths, or MCP credentials.

## Sources

- [prd.md](../prd.md)
- [sad.md](../sad.md)
- [us-lookup-user-devices.md](../user-stories/us-lookup-user-devices.md)
- Committed skill pack: `docs/.claude/skills/asset-ops/` and `docs/.claude/skills/device-lookup/` (`af27545`)
- Requestor notes 2026-08-29: Claude Code skills for non-developers; Slack-like CSV preview; automatic ServiceNow + Jamf + Intune lookup

## Assumptions

- Skill pack in-repo at `docs/.claude/skills/` is authoritative. Steps 1–4 use passkey scripts, not MCP (except optional step 1.5).
- "Look them up individually" for four pasted names means one CSV row per device from `asset-ops`, not four `device-lookup` chat novels.
- Spreadsheet paste is satisfied by TSV copy plus CSV download; Excel/Google Sheets deep links are not required for MVP.
- Defaulting unmatched device-lookup prose to this skill is acceptable while it is the only enabled lookup workflow.

## Open Questions

1. Pilot CSV column set beyond the minimum list in §5.
2. Are emails, `DOMAIN\sam`, and display names in scope for identity extraction?
3. Should a second enabled skill (for example app health) require an explicit chip, or is classifier disambiguation required in MVP?
4. Preview row cap: 10 vs Slack’s larger snippet for wide tables.

## Audit

- 2026-08-29 | `system-arch` | `create-sfs` | Specified lookup-user-devices.
- 2026-08-29 | `system-arch` | `update-sfs` | Aligned with session-host MVP: MCP ≤4, host scripts >4, `chat.csv_preview`, runtime `claude-agent-sdk`.
- 2026-08-29 | `system-arch` | `align-skill-pack` | Name lists (including 4) are `asset_ops` host scripts; MCP is `device_lookup` for one identifier. Columns match asset-ops step 1+2.
