---
name: jamf-api-patterns
description: "Jamf MCP tool-call quirks — readback gaps, write preflight, bulk static-group traps, JRA connectivity. Load alongside any domain skill doing Jamf write ops or bulk reads."
argument-hint: "tool call or symptom"
user-invocable: true
---

# Jamf API Patterns

Use this skill whenever running a `jamf_*` write operation or bulk read.

---

## Full Playbook

# Jamf API Patterns Skill

## Overview

Cross-domain Jamf MCP tool-call quirks — behavior gaps between what a tool call returns
and what actually happened. Load alongside any domain skill (`vulnerability-remediation`,
`asset-ops`, ...) that performs Jamf write operations or bulk
reads; this skill is the shared substrate, not a triage domain itself.

**Load this skill when:** running any `jamf_*` write operation, verifying a policy/scope
change, or doing bulk static-group work.
**Do NOT use for:** script-environment gotchas (`jamf-script-patterns`) or pkg builds
(`build-macos-pkg`).

---

## Prerequisites

- **MCP servers:** Jamf
- **Data to gather first:** the exact write op the ticket needs, and whether it targets
  a single device, a static group, or a bulk list of serials

---

## Failure Patterns

### Pattern 1: `jamf_policy_add_scope` readback looks empty after success

**Indicators:** Tool call returns success, but `jamf_get_policy_details` still shows
`computerGroupIds: []`.

**Root Cause:** Representation gap in the readback endpoint, not a failed write.
`jamf_policy_add_scope` is additive and never removes existing scope.

**Remediation:** Trust the tool's success response over a stale-looking readback; if in
doubt, re-verify a few minutes later or check via `jamf_get_computer_full_context`
instead of policy details.

---

### Pattern 2: Extended triage on a write op that isn't actually available

**Indicators:** Diagnostic work drags on before discovering the required write function
isn't exposed in the current MCP runtime (this pattern separated a slow ticket, CPE-4028,
from a fast one, CPE-4055).

**Remediation:** Before running device/history diagnostics, confirm the exact write op is
visible in current runtime. Sequence: parse the instruction → `jamf_policy_add_scope` →
policy readback verification → Jira update. If the op isn't exposed, request an MCP/
runtime refresh immediately instead of extending triage. Treat scope updates as
idempotent — `"already_in_scope"` with a readback confirming the target group present is
a valid completion state, not a failure.

---

### Pattern 3: Bulk static-group PUTs eating call volume on unmanaged serials

**Indicators:** High `group_put`/`computer_get` call counts and repeated Classic API
`409 unmanaged IDs` retries on a bulk sync.

**Root Cause:** Attempting to add unmanaged devices to a static group via the Classic
API.

**Remediation:** Request `section=GENERAL,HARDWARE` during inventory validation, inspect
`general.remoteManagement.managed`, and skip/count any `managed == false` serial in
preflight before the push. On CPE-4060 this took end-to-end runtime from 329.42s to
217.51s, `group_put` 31→14, `computer_get` 47→1.

---

### Pattern 4: Newly created static group returns transient 404

**Indicators:** A static group appears in Modern API listings immediately after creation
but a Classic API read (`/JSSResource/computergroups/id/{id}`) returns a transient `404`.

**Remediation:** Retry/backoff on group reads (401/404). For deterministic perf testing,
prefer a known-good existing target group that can be cleared and reused instead of a
freshly created one.

---

### Pattern 5: `jamf_create_policy` trigger not actually applied

**Indicators:** Policy created successfully but trigger/scope doesn't match what was
requested.

**Root Cause:** `jamf_create_policy` trigger params aren't reliably applied.

**Remediation:** ALWAYS call `jamf_get_policy_details` after `jamf_create_policy` to
verify scope and trigger. If wrong, fix and escalate — this is a known tool gap, not
user error. The `scope_device_serials` param on policy creation is also silently ignored;
follow up with `jamf_policy_add_scope` separately.

---

### Pattern 6: "Did the policy run" is the wrong question when logs are unavailable

**Remediation:** Verify outcome, not execution log visibility:
`jamf_get_computer_full_context(serial, sections=["APPLICATIONS"], app_filter="<app>")` —
if the device has the desired app version, remediation succeeded regardless of log
visibility. `installer -pkg` postinstall logs land in on-device `/var/log/install.log`,
never in Jamf policy logs — pair a pkg with a separate validation-script policy if fleet
visibility into install outcomes is required.

---

### Pattern 7: Smart group name doesn't match its actual criteria

**Indicators:** A policy scoped to a smart group affects the wrong devices.

**Remediation:** ALWAYS verify group criteria with `jamf_get_computer_group_details`
before scoping a policy to it — names can be stale or simply wrong (e.g. a group named
"Cursor Ai copy", ID 1252, that actually targets Claude for Desktop).

---

## Connectivity — Jamf Remote Assist (JRA)

Port 5555 failing a reachability test doesn't always mean a hard fail — JRA can still
connect intermittently at poor quality, then fail on a subsequent attempt. A 443 fallback
path exists in some environments but isn't reliable for production-quality remote
assist. Treat outbound `*.jra.services.jamfcloud.com:5555` as a required allow for stable
JRA performance, not a nice-to-have.

---

## Jira Handoff — Jamf Script URL Format

When linking a script in a Jira comment, use the canonical URL pattern — don't guess a
legacy path:
```
https://jamf.docusignhq.com:8443/view/settings/computer-management/scripts/<script_id>?tab=general
```
Avoid posting guessed legacy paths (e.g. `/scripts.html?id=`).

---

## Escalation Criteria

- A required write op is missing from the current MCP runtime after a refresh request
- Classic API 409s persist after the unmanaged-serial preflight filter is applied
- A policy's trigger/scope still doesn't match after the post-create verification step

---

## Standalone Mode

Without MCP, this skill still tells you which readback to trust vs. distrust and what
preflight to run before a bulk write — the actual calls require MCP.

---
*Last verified: 2026-08-18 | Owner: CPE Team*
