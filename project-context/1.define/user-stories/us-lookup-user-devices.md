# US-LOOKUP-USER-DEVICES: Look up users' devices

## 1. Story Identity

- **ID**: US-LOOKUP-USER-DEVICES
- **Title**: Look up users' devices from chat
- **Priority**: Must
- **Persona**: Workspace User (endpoint operations analyst or service-desk operator who is not a developer)

## 2. Narrative

As a Workspace User, I want to type a request such as "look up these users devices" and paste names so that Fleet Recon automatically collects ServiceNow, Jamf, and Intune device evidence, shows a spreadsheet-ready CSV preview in chat, and lets me download or copy it without using Claude Code, Python, or vendor consoles.

## 3. Acceptance Criteria

1. Given a message that matches the `lookup-user-devices` skill plus a pasted name list (including 1–4 unique valid identities), when I send it, then the system binds `asset_ops`, runs host-invoked `asset_report_build` then `asset_report_mdm`, and does not send the name list or CSV body into the LLM context.
2. Given the same skill plus any CSV upload (or a larger name list), when I send it, then the system uses the same two scripts and still does not send the name list into the LLM context.
3. Given a single serial, hostname, or username with no list, when I send it, then the system binds `device_lookup` MCP and does not run the CSV pipeline.
4. Given instruction prose such as "look up these users devices" mixed with names, when the request is parsed, then instruction words are not treated as usernames.
5. Given a completed or partial `asset_ops` run, when results exist, then chat renders a Slack-style CSV attachment (filename, row count, column headers, first preview rows, copy, download). Canvas is not required.
6. Given a connector outage, when other sources succeed, then the CSV still downloads with explicit per-source error or not-found columns and the run is `partial`, not discarded.
7. Given a Workspace User, when they use this skill, then they never see scripts, SKILL.md, credentials, or tool-configuration screens.

## 4. Scope Notes

- **In Scope for MVP**: Skill binding (`asset-ops` for lists, `device-lookup` for one id), ServiceNow + Jamf + Intune collection for this skill, chat CSV artifact with preview/copy/download.
- **Deferred**: `asset_report_app` (application health is a separate skill); Cortex XDR and Tenable on this skill; canvas as the primary result surface; free-form Claude Code shell; user-uploaded unreviewed scripts; `jamf_group_sync` without confirmation.

## 5. Traceability

- **PRD Anchors**: FR-1, FR-2, FR-3 (skill-scoped), FR-10, §3.2 Investigate a Small Set / Process a Batch, MVP AC 1–3, 8.
- **Related SFS**: `project-context/1.define/sfs/lookup-user-devices.md`

## Sources

- Requestor goal: package Claude Code skills/workflows for non-developers (2026-08-29).
- [prd.md](../prd.md), [sad.md](../sad.md).
- Prior script review recorded in SAD Sources (`asset_report_build.py`, `asset_report_mdm.py`).

## Assumptions

- The skill pack `docs/.claude/skills/` on `origin/master` `af27545` is authoritative.

## Open Questions

- Exact CSV columns required for the pilot spreadsheet (serial, platform, MDM last check-in, compliance, CMDB state, and which optional fields).
- Whether display names / emails are accepted identities in addition to usernames.

## Audit

- 2026-08-29 | `system-arch` | `create-stories` (supporting SFS) | Created from requestor skill-packaging goal and existing PRD dual-engine routing.
- 2026-08-29 | `system-arch` | `align-skill-pack` | Four pasted names use `asset_ops` scripts, not MCP fan-out.
