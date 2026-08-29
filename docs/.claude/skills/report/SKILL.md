---
name: report
description: Generate an HTML report for the current session's work. Emits to ~/work/logs/CPE-XXXX/report.html or ~/work/reports/ and opens in browser.
argument-hint: ""
user-invocable: true
---

# /report - Generate HTML Report

Generate a stakeholder-readable HTML report from the current session's work.

## Steps

1. **Determine context** — look at what was worked in this session:
   - Which CPE ticket(s) were active?
   - What tool calls were made (Jamf, Tenable, ServiceNow)?
   - What was the outcome?

2. **Choose the right template:**
   | Context                        | Template                                  | Output path                              |
   |-------------------------------|-------------------------------------------|------------------------------------------|
   | Single CPE ticket              | `${CLAUDE_SKILL_DIR}/templates/ticket-report.html`     | `~/work/logs/CPE-XXXX/report.html`       |
   | CVE / Tenable work             | `${CLAUDE_SKILL_DIR}/templates/cve-triage.html`        | `~/work/reports/cve-CVE-ID-YYYY-MM-DD.html` |
   | Fleet compliance (Zscaler/FV) | `${CLAUDE_SKILL_DIR}/templates/compliance.html`        | `~/work/reports/<kind>-YYYY-MM-DD.html`  |
   | Asset ops pipeline (`asset_report.csv`) | `${CLAUDE_SKILL_DIR}/templates/asset-ops.html` — **do not hand-fill; run `${CLAUDE_SKILL_DIR}/../asset-ops/scripts/asset_report_html.py`** | `~/work/reports/<source>-YYYY-MM-DD-HHMM.html` |
   | Canary rollout                 | `${CLAUDE_SKILL_DIR}/templates/canary-dashboard.html`  | `~/work/logs/CPE-XXXX/canary-YYYY-MM-DD.html` |
   | General / multi-ticket         | `${CLAUDE_SKILL_DIR}/templates/ticket-report.html`     | `~/work/reports/session-YYYY-MM-DD.html` |

3. **Read the template** (`Read ${CLAUDE_SKILL_DIR}/templates/<name>.html`)

4. **Fill all `{{PLACEHOLDERS}}`** with real session data:
   - `{{TICKET_KEY}}`, `{{TICKET_TITLE}}` — from Jira context
   - `{{DATE}}`, `{{DATETIME}}` — today's date / current time
   - `{{VERDICT_HEADLINE}}`, `{{VERDICT_BODY}}` — one-sentence outcome
   - `{{COMPLETED_LIST}}` — what was done
   - `{{PENDING_CONTENT}}` — next steps
   - `{{TIMELINE_EVENTS}}` — dated events from this session
   - `{{DEVICE_ROWS}}` — device table rows if applicable
   - `{{COPY_BACK_PROMPT}}` — what the user should paste to continue
   - All other placeholders based on context

5. **Write the file** using Write tool

6. **Open in browser**: `open <output-path>`

7. **Report back**: one line — "Report saved → <path>"

## Rules
- CSS is inlined from the template — never link to external files
- HTML generation is the **last step** — gather all data before writing
- Copy-back block is mandatory — what to paste to continue
- Snapshots: data reflects session state at generation time, not live
- If output < 25 lines with no structure, stay in chat instead (say so)
