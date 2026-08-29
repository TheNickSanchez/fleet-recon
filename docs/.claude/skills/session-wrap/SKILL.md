---
name: session-wrap
description: "End-of-session closeout. Use for 'wrap up', 'end of day', task completion — updates ticket logs and a structured journal line per ticket. Fast by default: HTML reports, the doc-integrity check, and retrospectives only run when actually warranted."
argument-hint: "tickets touched this session"
user-invocable: true
---

# Session Wrap

Use this skill to close out a work session cleanly.

---

## Full Playbook

# Session Wrap Skill

## Overview

End-of-session closeout procedure. Updates ticket logs and appends one structured
journal line per ticket. Deliberately lean — the previous version generated an HTML
report and a prose retrospective paragraph every time, unconditionally; both are now
on-demand, because most sessions don't need either.

**Load this skill when:** the user says "wrap up", "wrap this session", "end of day",
or a task reaches completion and you're closing out.
**Do NOT use for:** mid-session state saves or single-ticket log updates (just edit the
`log.md` directly).

Execute Steps 1–2 always. Steps 3–4 only when their condition is actually true — don't
manufacture a retrospective or run the linter just to fill the step.

**Parallelization rule:** Read all wrap inputs in one batch — `log.md` for every touched
ticket, fetched together, not sequentially.

---

## Step 1 — Ticket logs (for every ticket touched this session)
1. Overwrite `Current State` in `~/work/logs/CPE-XXXX/log.md` — one paragraph, present tense
2. Append a dated entry to `Work Log`
3. Verify `Artifacts` list matches physical files in the folder (`ls ~/work/logs/CPE-XXXX/`)
4. If ticket reached a stopping point → add a Jira comment using the Jira Commenting
   Protocol (see `ticket-workflow` skill)
5. **Do not** render `report.html` here. If a stakeholder-facing report is actually
   wanted — ticket closed, or explicitly asked for — use the `report` skill directly,
   separately from wrap.

## Step 2 — Journal line (always, one line per ticket, no prose paragraph)
Append to `~/work/state/JOURNAL.md`:
```
YYYY-MM-DD | CPE-XXXX | status — one-line detail
```
`status` is one of `done` / `blocked` / `parked`. This is the canonical JOURNAL.md
format — every other skill that appends here (`ticket-workflow` close sequence,
`vulnerability-remediation` Step 4) uses this same line shape. Keep the detail to one
clause; the ticket's own `log.md` already carries the full prose.

## Step 3 — Learnings (only if something new actually surfaced this session)
1. New script pattern, API quirk, or failure mode → update the corresponding skill file
   directly (Self-Improving Skill Protocol in `PORTABLE.md`) — not a scratchpad.
2. New API/tool gap hit → append to `GAPS.md` with Proposed Solution.
3. Nothing new? Skip both — don't pad this step.

## Step 4 — Retrospective (only when there's a real lesson — not every session)
Skip by default. Write one when something concrete is worth carrying forward — a
failed pattern, an avoidable round-trip, a time-saving discovery. When you do, append
to JOURNAL.md in the same line format:
```
YYYY-MM-DD | RETRO | one-line lesson
```
One line, not a paragraph. If it doesn't fit in one line, it belongs in `GAPS.md` or a
skill update (Step 3) instead, not here.

## Step 5 — Doc integrity check (only if a skill file was edited this session)
Run `python3 ${CLAUDE_SKILL_DIR}/../../scripts/check_skill_links.py` — fails on any dead
path reference within a skill's own folder. Skip entirely if no `skills/*/SKILL.md` was
touched this session; nothing could have gone stale.

## Step 6 — Confirm wrap
Output one line: `Wrap complete — [date]. Tickets touched: [CPE-XXXX, ...]. Next: [what to pick up tomorrow].`

---

## Journal pruning (every ~2 weeks)
When JOURNAL.md exceeds ~100 lines, archive old entries to
`~/work/logs/journal-archive-YYYY-MM-DD.md` and start a clean slate. The structured
line format makes this a plain `head`/`tail` split — no need to parse prose paragraphs
to find where a date boundary falls.

## Report cleanup (occasionally, not every wrap)
Prune `~/work/reports/*.html` older than 30 days when you notice the folder getting
large — `find ~/work/reports -name "*.html" -mtime +30 -delete`. Not a per-session
step; on-demand reports accumulate slowly enough that this doesn't need to run every
wrap. Per-ticket `report.html` files in `~/work/logs/` are never pruned regardless —
they stay with the ticket folder.

---

## Standalone Mode

Without MCP connections, this skill still runs fully — it operates on local files
(`~/work/logs/`, `~/work/state/`). The only step needing MCP is the optional Jira
comment in Step 1.

---
*Last verified: 2026-08-26 | Owner: CPE Team*
