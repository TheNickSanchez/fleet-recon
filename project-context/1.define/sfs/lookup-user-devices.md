# SFS: Look up users' devices

## Context & Instructions

This System Functional Specification defines the first packaged Claude Code skill that non-developers run from the Fleet Recon chat window: **look up these users' devices**. It is derived from the PRD dual-engine routing model, the SAD capability adapters for `asset_report_build` and `asset_report_mdm`, and the requestor’s 2026-08-29 product goal.

**PRD Document**: [prd.md](../prd.md) FR-1, FR-2, FR-3, FR-7, FR-10  
**User Story / Feature ID**: US-LOOKUP-USER-DEVICES  
**Selected Runtime**: `crewai`

### 1. Purpose and Scope

- **Feature ID**: `lookup-user-devices`
- **Purpose**: A Workspace User pastes a natural-language request and names (or a CSV). The product binds that request to a pre-registered skill, collects device evidence from ServiceNow, Jamf Pro, and Microsoft Intune using the approved Python capabilities, and returns a spreadsheet-ready CSV in chat with a Slack-style preview and download. The user never runs Claude Code, Python, or vendor consoles.
- **In Scope**: Intent/skill binding; identity extraction distinct from instruction prose; routing threshold of 4 unique identities; micro-query per-identity connector calls; batch CSV materialization into `asset_report_build` → `asset_report_mdm`; identical CSV schema on both routes; chat artifact card; canvas persistence of the same rows; partial-failure columns.
- **Out of Scope**: `asset_report_app` / application-health lookup; Cortex XDR and Tenable on this skill; mutation/remediation; arbitrary shell or unreviewed script execution; LLM-driven per-name tool looping.

### 2. Traceability

- **PRD Anchors**: FR-1 Request Intake; FR-2 Dual-Engine Routing (threshold 4); FR-3 Connector Collection skill-scoped to ServiceNow, Jamf, Intune; FR-7 registered `asset_report_build` and `asset_report_mdm`; FR-10 Chat Result Artifacts; MVP AC 1–3, 8.
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

End-to-end processing is deterministic application-service work. CrewAI does not iterate names or choose connectors.

1. **Authenticate and correlate.** FastAPI authenticates the actor, binds `workspace_id`, and creates `correlation_id`.
2. **Resolve skill.** `SkillMatcher` scores the text (and optional client `intent`) against the workspace-enabled workflow catalog. `lookup-user-devices` matches phrases such as "look up these users devices", "lookup users devices", "find devices for", and the empty-state chip. If no skill matches and identities are present, default this MVP skill only when the workspace has a single device-lookup workflow enabled; otherwise ask the user to pick a skill and do not call connectors.
3. **Extract identities separately from instructions.** Strip matched trigger spans and a fixed instruction-stopword list (`look`, `up`, `lookup`, `these`, `those`, `users`, `user`, `devices`, `device`, `please`, …). Split remaining text on whitespace/commas/semicolons/newlines. Sanitize, validate, and case-insensitive-deduplicate. Persist `QueryRun` with `skill_id`, `input_kind`, `input_count`, `rejected_count`, and `mode`.
4. **Route (after sanitization, never mid-run).**
   - 1–4 unique identities and not a CSV upload → `micro_query`.
   - 5+ unique identities or any CSV upload → `batch_automation`.
5. **Do not put names in the model.** Orchestrator/Analysis context contains `skill_id`, `run_id`, `mode`, `input_count`, connector health summaries, and later redacted evidence references. The identity list lives in `query_run_input` / object storage only.
6. **Micro-query (≤4).** The request worker calls the same Python adapters the scripts use, per identity, concurrently under connector rate limits:
   - `asset_report_build`: ServiceNow `sys_user` → assigned `alm_hardware` (or explicit no-device/not-found).
   - `asset_report_mdm`: macOS rows → Jamf inventory; Windows rows → Intune serial/managed-device lookup; unknown platform → both with explicit unmatched state.
   Stream `chat.card` / `run.progress` as each identity/source completes. Persist `SourceEvidence` after each successful subject/source call.
7. **Batch (>4 or CSV).** Write an immutable sanitized username CSV (column `username`) to private object storage. Enqueue a job with `run_id`, object reference, `skill_id`, tool/configuration/credential snapshot. The worker runs `asset_report_build` then `asset_report_mdm` as the SAD dependency graph (checkpointed per subject/source). Progress events are counts and source milestones, not name lists.
8. **Materialize the chat CSV.** Both routes write one `ResultArtifact` (`text/csv`) from the joined normalized rows. Preview payload is the header plus the first 10 data rows (configurable, max 25) and does not include raw vendor payloads or secrets.
9. **Publish.** Persist artifact metadata, emit `chat.artifact`, update canvas work items from the same rows, mark run `completed` or `partial`. Analysis Agent may later attach findings; it must not block CSV delivery for this skill.

Claude Code mapping (packaging time, not runtime):

| Claude Code path | Product object |
| --- | --- |
| `.claude/skills/asset-ops/SKILL.md` | `WorkflowDefinition` `lookup-user-devices` (triggers, description, required tools) |
| `scripts/asset_report_build.py` | `ToolDefinition` `asset_report_build` |
| `scripts/asset_report_mdm.py` | `ToolDefinition` `asset_report_mdm` |
| `scripts/asset_report_app.py` | Separate future workflow; not invoked by this skill |

### 5. Outputs

- **`QueryRunSummary`**: Existing fields plus `skill_id` and `artifact_id` when present.
- **SSE `chat.artifact`**: `artifact_id`, `filename`, `media_type`, `row_count`, `byte_size`, `preview_headers`, `preview_rows`, `truncated`, `download_path`, `correlation_id`.
- **CSV file**: One row per device (or one explicit no-device/not-found row per identity). Minimum columns: `username`, `serial`, `hostname`, `model`, `manufacturer`, `platform`, `cmdb_state`, `mdm_provider`, `mdm_status`, `last_check_in`, `compliance`, `source_errors`, `retrieved_at`. Exact extra columns follow the adapters' typed evidence, not free-form LLM text.
- **Chat UI**: Slack-style file card — file icon, filename (`devices-<run_short_id>.csv`), row count, header + preview table, "n more rows" if truncated, **Copy CSV**, **Copy for spreadsheet** (tab-separated), **Download**.
- **Canvas rows**: Same joined evidence; export of the filtered canvas must match artifact columns for the current filter set.
- **Partial run**: CSV still produced; `source_errors` and per-row MDM/CMDB status carry safe error categories.

### 6. Validations and Constraints

- Routing uses unique sanitized identity count, not raw token count and not instruction-word count.
- `MICRO_QUERY_MAX_SUBJECTS = 4`. Five identities always batch.
- This skill may invoke only `asset_report_build` and `asset_report_mdm`. Cortex, Tenable, and `asset_report_app` are not in the skill’s tool set.
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
| One source fails | Run `partial`; CSV includes error/not-found columns | Other sources continue |
| All sources fail | Run `failed`; chat error card; no successful artifact, or empty artifact with error rows only if any identity was attempted | Bounded retries per connector `retry_safe` |
| Disabled/unhealthy required tool | Safe explanation; blocked or partial per dependency policy | Do not invoke the disabled tool |
| Schema-invalid agent output | Ignored for this skill’s CSV path; CSV still ships from Python adapters | Analysis retry once, then skip analysis |

CrewAI halt/retry follows the adapter rule: invalid structured output is retried once; a second failure fails the analysis task only. Collection and artifact write do not depend on the LLM.

### 8. Acceptance Criteria

1. "look up these users devices" plus 4 valid names → `micro_query`, `input_count=4`, instruction words not in the identity list, ServiceNow + Jamf/Intune adapters invoked, CSV artifact preview in chat.
2. Same prompt plus 5 valid names → `batch_automation`, internal username CSV created, `asset_report_build` then `asset_report_mdm` executed, names absent from Prompt Trace.
3. CSV upload with this skill (chip or inferred) → batch regardless of row count; result CSV is the device report, not a round-trip of the upload.
4. Copy CSV places RFC 4180 text on the clipboard; Copy for spreadsheet places tab-separated rows; Download returns `text/csv` with `Content-Disposition` filename.
5. Preview shows at most 10 data rows and a truncated count; download has all rows.
6. Workspace User cannot read SKILL.md, script paths, or credentials; Administrator tool catalog still shows the two registered capabilities.
7. Unit tests: instruction-word stripping; threshold 4 vs 5; skill tool allowlist; artifact preview cap. Integration tests: fixture adapters for ServiceNow, Jamf, Intune produce a joinable CSV.

QA mapping: `*test-unit` on matcher, sanitizer, router, artifact preview; `*test-integration` on the two-step adapter pipeline with vendor fixtures.

## Sources

- [prd.md](../prd.md)
- [sad.md](../sad.md)
- [us-lookup-user-devices.md](../user-stories/us-lookup-user-devices.md)
- SAD-reviewed scripts: `asset_report_build.py`, `asset_report_mdm.py` (requestor path `.claude/skills/asset-ops/scripts` was not available in this environment)
- Requestor notes 2026-08-29: Claude Code skills for non-developers; 4-name vs CSV-script split; Slack-like CSV preview; automatic ServiceNow + Jamf + Intune lookup

## Assumptions

- `/Users/nick.sanchez/development-test2` was not readable here. The three report scripts already incorporated in SAD §2.2 are treated as the asset-ops skill scripts.
- "Look them up individually" means per-identity Python connector calls, not an LLM calling a tool once per name.
- Spreadsheet paste is satisfied by TSV copy plus CSV download; Excel/Google Sheets deep links are not required for MVP.
- Defaulting unmatched device-lookup prose to this skill is acceptable while it is the only enabled lookup workflow.

## Open Questions

1. Pilot CSV column set beyond the minimum list in §5.
2. Are emails, `DOMAIN\sam`, and display names in scope for identity extraction?
3. Should a second enabled skill (for example app health) require an explicit chip, or is classifier disambiguation required in MVP?
4. Preview row cap: 10 vs Slack’s larger snippet for wide tables.

## Audit

- 2026-08-29 | `system-arch` | `create-sfs` | Resolved `AAMAD_TARGET_RUNTIME=crewai` from `aamad.config.yml`. Specified skill binding, 4-subject routing, token isolation, ServiceNow/Jamf/Intune adapter pipeline, and chat CSV artifact for US-LOOKUP-USER-DEVICES. Prompt Trace omitted: this SFS is a specification, not a runtime model invocation.
