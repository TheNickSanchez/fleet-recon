---
name: sprint-brief
description: "Pull current sprint Jira work and present it grouped by status with a suggested priority order. Use for 'pull up my sprint', 'what's on my plate', 'sprint status' — no specific ticket named."
argument-hint: ""
user-invocable: true
---

# Sprint Brief

Use this skill for a quick read of the current sprint — no ticket name, no report file.

---

## Full Playbook

# Sprint Brief

## Overview
- **Use when:** the user asks to pull up their sprint, check status, or "what's on my
  plate" — no specific ticket named.
- **Do NOT use for:** working a named ticket end-to-end -> Handled by: `ticket-workflow`.

## Procedure
1. Call tool `jira_get_my_sprint_work`.
2. Group tickets by status in this exact order: **In Progress**, **Blocked**, **Ready
   for Review**, **To Do**. Omit empty status headers.
3. Within each status group, sort tickets internally by priority (`P1` -> `P5`).
4. Format all ticket keys as clickable Markdown links using base URL
   `https://docusign.atlassian.net/browse/CPE-XXXX`.
5. Select 3–5 high-priority, non-blocked actionable tasks for the "Suggested Tackle
   Order".
6. Strictly avoid raw bullet dashes `-` or interactive checkboxes `[ ]` before ticket
   links in the status sections — start each line directly with the link.

## Output Format

```markdown
### 🎯 Suggested Tackle Order
1. **[CPE-XXXX](https://docusign.atlassian.net/browse/CPE-XXXX)** `P1` — Brief Summary
2. **[CPE-YYYY](https://docusign.atlassian.net/browse/CPE-YYYY)** `P2` — Brief Summary

---

### 🔄 In Progress
**[CPE-XXXX](https://docusign.atlassian.net/browse/CPE-XXXX)** `P1` — Ticket Summary
**[CPE-YYYY](https://docusign.atlassian.net/browse/CPE-YYYY)** `P3` — Ticket Summary

### 🛑 Blocked
**[CPE-ZZZZ](https://docusign.atlassian.net/browse/CPE-ZZZZ)** `P2` — Ticket Summary — *Blocker note if available*

### 👀 Ready for Review
**[CPE-WWWW](https://docusign.atlassian.net/browse/CPE-WWWW)** `P3` — Ticket Summary

### 📋 To Do
**[CPE-AAAA](https://docusign.atlassian.net/browse/CPE-AAAA)** `P4` — Ticket Summary
```

## Standalone Mode
Without MCP, ask the user to paste their sprint board export or ticket list, then apply the
same grouping/sorting/output rules above.

---
*Last verified: 2026-08-19 | Owner: CPE Team*
