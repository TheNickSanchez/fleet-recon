---
name: ticket-workflow
description: "Work a CPE Jira ticket end to end. Use when the user names a ticket ('work on CPE-XXXXX') — pull from Jira, maintain ticket log, load domain skill, run write-op preflight, write Jira comments, close out."
argument-hint: "CPE ticket key"
user-invocable: true
---

# Ticket Workflow

Use this skill when actively working a CPE Jira ticket.

---

## Full Playbook

# Ticket Workflow Skill

## Overview

End-to-end execution protocol for CPE Jira tickets: pull data, maintain the internal log,
run write-op preflight safely, format external Jira comments, and close out.

**Load this skill when:** the user names a ticket ("let's work on CPE-XXXXX"), you're actively
executing ticket work, or you're writing a Jira comment/description tied to a ticket.
**Do NOT use for:** a bare lookup (serial/user/device) with no ticket attached — use
`device-lookup` and don't create a log for a ticket you're just glancing at.

---

## Procedure

### Phase 0 — Discovery gate (new Mac tickets only)

Before any write action on a **new, undiscovered** Mac finding (no existing log entry, no
approved plan yet), run this gate. Skip it for Windows-only tickets (route to the Intune-side
workflow) or a ticket whose `log.md` already shows discovery done (Current State says the
plan is approved) — go straight to Step 5 below.

1. **Open the ticket.** `jira_get_issue(key)` + `jira_get_comments(key)`. Extract: Finding
   Description, Solution/remediation guidance, CVE (if any), affected platform hints in the
   title (`(Unix)`, `(Windows)`, `macOS`, hostname prefixes in comments — `dsa*` = Mac,
   `dsw*` = Windows).
2. **Confirm it's a Mac ticket.**
   - Title says `(Unix)`/`(macOS)` or comments reference `dsa*` hosts → proceed.
   - Title says `(Windows)` or references `dsw*` hosts only → **stop**, this belongs to the
     Intune-side workflow, tell the user and don't touch Jamf.
   - Ambiguous (no OS marker, generic finding) → ask the user to confirm platform before
     spending Jamf calls on it.
3. **Jamf discovery — read-only, no writes.** Run in parallel:
   - `jamf_search_policies(search_term=<app or CVE keyword>)`
   - `jamf_list_scripts(search_term=<app or CVE keyword>)`
   - `jamf_list_computer_groups(search_term=<app or CVE keyword>)`

   If any hit, pull full context before summarizing (still read-only):
   - `jamf_get_policy_details(policy_id)` — enabled?, trigger, scope, attached script(s)
   - `jamf_get_script_details(script_id)` — does the script content actually address this
     finding, or is it stale/unrelated?
4. **HALT — human-in-the-loop gate.** Do not create a policy, script, group, or scope
   change. Compile the Discovery Summary (format below) and stop for the user's go-ahead.
   Do not scaffold `~/work/logs/CPE-XXXX/log.md` until after the user approves a
   direction — the summary itself is the output of this pass.
5. **After approval,** continue with Step 2 below (scaffold the log with the agreed plan as
   Current State) and hand off to `vulnerability-remediation` Phase 3a/3b/4 for the actual
   build-or-fix-or-monitor work.

**Composes with:** `vulnerability-remediation` (Phases 3+ once this gate clears),
`jamf-api-patterns`.

#### Discovery Summary Format

```markdown
### CPE-XXXX — [Ticket Summary]

**Vulnerability:**
[What the finding is, in plain terms — what's exposed and why it matters.]

**Fix:**
[Vendor/Nessus-recommended remediation — upgrade, remove, patch, config change.]

**Discovery Results (Jamf):**
- Policy: [name/ID, enabled?, trigger, scope target] or "No existing policy found."
- Script: [name/ID — does its logic match the fix above?] or "No existing script found."
- Smart/Static Group: [name/ID, member logic] or "No existing group found."
- Assessment: [does existing tooling already cover this, is it stale, or is this net-new?]

**Awaiting:** go/no-go on [proposed direction — e.g. "scope existing policy 1488 to the
Tenable-affected group" or "build new remediation, no existing coverage"].
```

#### Worked Example — CPE-4160

**Vulnerability:** Oracle Java JRE installations no longer receive vendor security
patches (Nessus/DTS Endpoints finding, plugin 64816). Any Oracle JRE build past its
support window is presumed vulnerable — the finding doesn't cite a specific CVE.

**Fix:** Remove unsupported Oracle Java JRE from affected Macs (or upgrade to a
supported build/vendor if the host needs Java at all). Non-Oracle JDKs (Corretto, Zulu,
Temurin, etc.) are out of scope for this fix.

**Discovery Results (Jamf):**
- Policy: ID 1488, "Oracle Java Removal and Notification" — **enabled**, trigger
  `checkin`, frequency once-per-computer, scoped to `computerGroupIds: [1]` (All Managed
  Clients).
- Script: ID 646, same name — scans the full disk for Java homes, identifies vendor via
  `release`/`Info.plist`, removes Oracle-vendor installs only, keeps non-Oracle JDKs,
  notifies the user via jamfHelper. Logic matches the fix.
- Smart Group: ID 1482, "Oracle Java" (smart) — exists as a detection group, not used as
  the policy's scope target.
- Assessment: coverage already exists and is broadly scoped (checkin trigger, all
  managed clients). This looks like an already-active remediation, not a net-new build —
  next step is confirming affected devices are actually checking in and clearing, not
  building anything new.

**Awaiting:** go/no-go on pivoting to verification (pull affected host list from the
ticket/Tenable, spot-check via `jamf_get_computer_history` that policy 1488 ran and Oracle
Java is gone) rather than treating this as a build-from-scratch remediation.

#### Standalone Mode (Phase 0)

Without MCP, ask the user to paste the ticket text and any known Jamf policy/script/group
names, then apply the same Discovery Summary format from what's pasted.

---

### Step 1 — Pull from Jira (always)
```
jira_get_issue(key) + jira_get_comments(key)
```
Jira is the source of truth for status, priority, description, and comments.

### Step 2 — Check for a ticket log
Does `~/work/logs/CPE-XXXXX/log.md` exist?
- **Yes → Read it.** The accumulated memory across all sessions. Current State tells you
  where things stand; Work Log tells you what's been tried.
- **No → Create it.** Scaffold from Jira data immediately: `mkdir ~/work/logs/CPE-XXXXX/`,
  then write `log.md` using the format below.

### Step 3 — Load the relevant fleet skill (if the ticket domain matches one)
For a **new** Mac finding with no prior discovery logged, run Phase 0 above first — it
gates on the user's go/no-go before any Jamf write, then hands off to the matching domain
skill (e.g. `vulnerability-remediation`).

### Step 4 — Execution preflight (required for Jamf/Intune write tasks)
- Confirm the exact write operation required by the ticket is available before deep triage.
- For Jamf scope updates, use `jamf_policy_add_scope` and verify with policy readback.
- If required write op is missing from current runtime, request tool/runtime refresh immediately.
- Apply the Safety Guardrails below before running any scoped write op.

### Safety Guardrails (all write ops)
- Autonomous canary actions are capped at **10 devices** maximum.
- Any scope expansion beyond 10 devices requires explicit human verification before running.

### Step 5 — Work the ticket

### Step 6 — Post Jira updates using the Commenting Protocol (below)
Any comment or description written during this pass follows the format in
**Jira Commenting Protocol** — not the internal log's terse style.

### Step 7 — Ticket micro-retro (every ticket pass)
Append a 3-line retro block to that ticket's Work Log entry:
- What went well
- What did not go well
- One concrete improvement to apply on the next pass

### Step 8 — Update the log before ending the session
- Overwrite the **Current State** section with where things stand now
- Append a dated entry to **Work Log**
- List any new files created in **Artifacts**

---

## Jira Commenting Protocol (External Record)

Jira is read by managers, stakeholders, and cross-team leads — not just engineers. Write
every comment and description as if the engineer's manager will read it and needs to understand
what's happening without any technical background. This applies to **any** Jira comment
or description written while working a ticket — it's not a separate step to remember.

**Do NOT use this style for `log.md`** — that stays terse, present-tense, internal.

### Principles
- **Lead with impact, not implementation.** "Zscaler is now enforcing SSL inspection on
  1,200 Mac endpoints" beats "Updated curl/npm/pip CA bundle paths via /etc/zshenv and
  per-tool config files."
- **Plain English for technical steps.** If you must mention a tool or command, follow it
  with what it does in parentheses. Past tense for completed work, present tense for
  current state.
- **Outcomes over actions.** "All 9 checks passed on the pilot device" beats "Ran the
  policy with sudo jamf policy -event arlo_test."
- **No internal IDs in headlines.** "Deploy Zscaler cert trust to pilot group" not "Attach
  script 639 to policy 1460 scope group."
- **Every status comment answers three questions:** What was completed? What is pending?
  Is anything blocked or needs a decision?

### Comment template (progress updates)
```markdown
**Status:** [one-line current state]

**Completed:**
- [Impact statement — what works now that didn't before]

**Pending:**
- [Next concrete step with owner if known]

**Blockers / Decisions needed:**
- [If any — otherwise omit this section]
```

### Description structure (new tickets)
- First paragraph: what problem this solves and who it affects
- Second paragraph: proposed approach in plain English
- Acceptance criteria: bullet list of what "done" looks like

### Reference conventions
- Child issue types: "child epic" means a Story under an epic; default to Story for children.
- Priority levels: P1 = fleet-wide outage, P2 = urgent, P3 = default.

---

## Ticket Log Format (`~/work/logs/CPE-XXXXX/log.md`)

```markdown
# CPE-XXXXX — [Jira summary line]

**Priority:** [P1–P5]  **Status:** [Jira status]  **Last touched:** [YYYY-MM-DD]

## Current State
[One paragraph. Where things stand RIGHT NOW. Overwrite this every session.
What's done, what's blocked, what's next. This is what gets read at session start.]

## Work Log

### YYYY-MM-DD
[What was done, decisions made, outcome, blockers hit.]

**Retro:**
- Went well: ...
- Needs work: ...
- Next improvement: ...

## Artifacts
[List files in this folder with a one-line description each.]
```

**Rules:**
- **Current State is always overwritten** — it reflects now, not history.
- **Work Log is append-only** — never edit past entries.
- **Jira comments are the external record.** The log is your internal scratchpad.
  Anything the user needs to see goes in Jira (per the Commenting Protocol above). Anything
  the agent needs to remember goes here.
- **Artifacts section** keeps the folder self-documenting — list every file.
- **Don't create the log for a ticket you're just looking up.** Only create it when
  actively working the ticket.

---

## Close Sequence Protocol

When the user says "close this ticket", execute in order:

1. Post a final progress update comment to Jira using the **Jira Commenting Protocol** format.
2. Transition the Jira ticket status to Closed/Done.
3. Finalize **Current State** in `~/work/logs/CPE-XXXXX/log.md`.
4. Rename the log folder: `mv ~/work/logs/CPE-XXXXX ~/work/logs/DONE-CPE-XXXXX-MMDDYYYY`.
5. Append a summary entry to `~/work/state/JOURNAL.md` — one line, `session-wrap`'s
   structured format: `YYYY-MM-DD | CPE-XXXXX | done — one-line detail`.

---

## Standalone Mode

Without MCP, this skill can still scaffold/maintain the local `log.md` structure and
produce ready-to-paste Jira comment/description text from pasted work notes. Steps 1 and 4
(Jira read, Jamf write preflight) and actually posting to Jira require MCP.

---
*Last verified: 2026-08-18 | Owner: CPE Team*
