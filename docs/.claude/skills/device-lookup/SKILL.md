---
name: device-lookup
description: "Resolve a serial number, device identifier, or username to full context across Jamf, Intune, ServiceNow, and Tenable. Use for a bare lookup with no ticket attached."
argument-hint: "serial, hostname, or username"
user-invocable: true
---

# Device Lookup

Use this skill for ad hoc serial/device/user lookups — no ticket, no write ops.

---

## Full Playbook

# Skill: Device Lookup

## Overview
Tool-chaining logic for resolving a serial number, hostname, or username across Jamf, Intune, ServiceNow, and Tenable.

- **Trigger**: Single serial number, device ID, hostname, or user lookup provided with NO active ticket attached.
- **Exclusion**: Do NOT load during active ticket triage — `ticket-workflow` owns in-ticket lookups.

---

## Tool Execution Matrix

When an identifier is provided, execute the primary tool **immediately without asking for confirmation or tool selection**:

| Input Type | Primary Execution (Run Immediately) | Conditional Fallback / Context Tool |
| :--- | :--- | :--- |
| **macOS Serial / Hostname** | `jamf_get_device_summary` | Run ServiceNow lookup ONLY if asset tag/owner context is requested or missing. |
| **Windows Serial / Hostname** | `intune_lookup_device` | Run ServiceNow lookup ONLY if asset tag/owner context is requested or missing. |
| **Vulnerability Assessment** | `tenable_lookup_device` | Chain immediately to `tenable_get_device_vulns` using the returned device ID. |
| **User Profile / Email** | `snow_lookup_user_profile` | Pull profile + assigned device list in a single turn. |

---

## Output Routing & Formatting

1. **Preserve Context**: Always output essential technical state (OS build, compliance status, last check-in timestamp, assigned user).

---
*Last verified: 2026-08-18 | Owner: CPE Team*
