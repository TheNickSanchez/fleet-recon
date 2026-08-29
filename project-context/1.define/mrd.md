# Fleet Recon Market Requirements Document

## 1. Executive Summary

Fleet Recon is an enterprise endpoint-reconciliation workspace for teams that must determine whether a person or device is present, managed, compliant, vulnerable, correctly owned, and accurately represented in the CMDB. It connects the operational evidence already held in ServiceNow, Cortex XDR, Jamf Pro, Microsoft Intune, and Tenable, then turns that evidence into shared, approval-governed work.

The product is not a new MDM, EDR, vulnerability scanner, CMDB, or ITSM suite. Its market position is the collaboration and decision layer between them: one place to investigate mismatches, assign ownership, preserve the resolution trail, and safely dispatch approved remediation.

## 2. Research Basis

This MRD uses primary vendor documentation to validate the problem environment, not to make third-party market-size claims:

- Microsoft documents that compliance is evaluated through platform-specific policies, device check-ins, and Conditional Access; a device with no policy can be treated differently by tenant policy. A single compliance label therefore needs operational context before it becomes a remediation decision.
- Jamf positions its platform across Apple device management, inventory, security visibility, and compliance. This confirms Apple management is a distinct operational system alongside Windows-centric management.
- Palo Alto Networks documents Cortex XDR as a correlated detection, investigation, and unified-response product. Its endpoint evidence is valuable to operations, but its primary workflow is security operations rather than CMDB reconciliation.
- Tenable documents exposure management, vulnerability management, endpoint agents, and third-party ITSM integrations. Exposure data is another time-sensitive evidence stream rather than a complete ownership or lifecycle record.
- ServiceNow describes CMDB as the system of record for configuration items; Fleet Recon treats it as an authoritative business record that must be reconciled against observed endpoint state, not overwritten autonomously.

The research establishes a multi-system operating reality. It does not prove a specific addressable-market size, competitor win rate, or ROI. Those are pilot-validation questions.

## 3. Market Problem

### 3.1 The Reconciliation Gap

Enterprise endpoint operations commonly split evidence across an asset system of record, one or more device-management systems, an endpoint-security platform, and a vulnerability platform. Each system has a legitimate but incomplete view:

| Evidence Domain | Typical System | What It Answers | What It Cannot Reliably Answer Alone |
| --- | --- | --- | --- |
| Asset and ownership record | ServiceNow CMDB | Who is assigned, lifecycle state, related ITSM history | Whether the device is currently active, enrolled, or compliant |
| macOS management | Jamf Pro | Apple enrollment, inventory, policy, and management state | Windows state, security telemetry, or CMDB accuracy |
| Windows/device compliance | Microsoft Intune | Platform policy and current reported compliance | Full vulnerability context, CMDB lifecycle, or Apple state |
| Endpoint detection and response | Cortex XDR | Telemetry, detection, investigation evidence | Authorized ownership, CMDB cleanup decision, work assignment |
| Exposure and vulnerability management | Tenable | Findings, scan/agent status, exposure context | MDM enrollment and business disposition |

The operator's work is not merely looking up a record. It is deciding which evidence is recent enough and authoritative enough to explain a discrepancy, coordinating a next step, and proving what was done. Today that often happens through exported reports, browser tabs, ad hoc scripts, spreadsheets, chat messages, and separately created tickets.

### 3.2 Consequences

- **Slow investigations:** Analysts repeat cross-system lookups for each person or device.
- **Stale decisions:** Static reports cannot show who has reviewed a row, what changed, or whether a remediation completed.
- **Duplicate or orphaned work:** Teams independently investigate the same device or pass incomplete context to service desks.
- **CMDB quality debt:** Discrepancies are discovered but not consistently assigned, tracked, or resolved.
- **Unsafe automation pressure:** Manual effort invites broad remediation actions without target review, approval, or a durable audit trail.
- **Uncontrolled AI cost and behavior:** Treating a 500-row cleanup like a conversational prompt creates avoidable token use and non-deterministic execution.

## 4. Target Market and Ideal Customer Profile

### Primary Segment

Mid-market and enterprise IT organizations with a mixed macOS and Windows fleet, an established ServiceNow CMDB, and at least three of the named endpoint/security systems. The initial customer should already have a recurring endpoint-hygiene or CMDB-reconciliation process and a responsible owner for remediation approvals.

### Buying Committee

| Role | Economic / Operational Interest | Buying Trigger |
| --- | --- | --- |
| VP / Director of IT Operations | Reduce operational delay, rework, and configuration-data risk | Recurring audit findings, poor CMDB trust, fragmented endpoint workflows |
| Endpoint Engineering Manager | Improve fleet coverage and safe remediation throughput | Mixed MDM estate, unmanaged-device backlog, recurring manual reporting |
| CMDB / IT Asset Manager | Improve record accuracy and evidence-based cleanup | Lifecycle/ownership discrepancy backlog and weak closure evidence |
| Security Operations or Vulnerability Lead | Prioritize endpoint exposure with management context | Findings cannot be quickly tied to active ownership and managed state |
| Service Desk Lead | Receive complete, assignable remediation work | Tickets lack device evidence or clear action ownership |
| Security / Compliance Reviewer | Ensure automation is governed and auditable | Need for scoped approvals, least privilege, and action records |

### Initial Adoption Profile

A strong design-partner customer has 500-10,000 managed endpoints, uses ServiceNow plus at least Jamf or Intune, can provide non-production connector access, and has a measurable monthly reconciliation workflow. The initial deployment is single-tenant with one operational user role; the designated administrator alone configures connectors and action allowlists.

## 5. User Jobs and Personas

| Persona | Job to Be Done | Current Workaround | Required Outcome |
| --- | --- | --- | --- |
| Endpoint Operations Analyst | When a list of people or devices needs review, quickly establish the actual endpoint state and hand off the right work. | Query consoles and merge exports manually. | Source-cited evidence, clear discrepancy category, and shared work state. |
| IT Asset / CMDB Manager | When inventory conflicts with observed endpoint state, decide whether and how to correct the record. | Spreadsheet exceptions and manual ticket follow-up. | Traceable cleanup queue with owner, rationale, and resolution state. |
| Security / Vulnerability Analyst | When an exposed endpoint is found, determine whether it is active, managed, and owned before escalating. | Pivot among security and MDM consoles. | Correlated endpoint posture and ranked, evidence-backed next action. |
| Service Desk Lead | When work is assigned, ensure the assignee receives a complete and auditable request. | Recreate context in tickets and chat. | Scoped assignment or ticket that links source evidence and requested outcome. |

## 6. Value Proposition

**For endpoint operations teams managing a fragmented enterprise fleet, Fleet Recon is a shared endpoint-reconciliation workspace that converts multi-source evidence into governed work. Unlike spreadsheets, static HTML reports, or isolated product dashboards, it preserves provenance, synchronizes team decisions in real time, selects deterministic batch execution for large requests, and requires approval before consequential action.**

### Customer Value Hypotheses

| Value Hypothesis | Mechanism | Pilot Evidence Needed |
| --- | --- | --- |
| Investigations finish faster | One normalized view replaces repeated manual pivots. | Median time from request acceptance to decision, compared with baseline. |
| More discrepancies reach closure | Assignment, notes, and cleanup state remain shared and durable. | Closure rate and aging of CMDB discrepancy work items. |
| Remediation is safer | Preview, approval, allowlists, and receipts gate state-changing actions. | Percentage of mutations with complete approval/audit chain; target 100%. |
| AI cost remains controlled | Name-list lookups run host-invoked asset-ops scripts; the model reads stdout summaries, never the CSV body. Single-id lookups use MCP. | Model tokens and connector calls per run by skill bind. |
| Security and IT cooperate better | Findings retain source and freshness context across domain boundaries. | Percentage of selected findings with sufficient evidence to make an ownership decision. |

## 7. Product Positioning and Alternatives

| Alternative | Strength | Gap Fleet Recon Addresses |
| --- | --- | --- |
| Static scripts, spreadsheets, and HTML reports | Fast to create for one-off data pulls | No shared live state, durable action workflow, provenance model, or safe dispatch |
| Native vendor dashboards | Deep source-specific controls | No unified endpoint decision record across CMDB, MDM, EDR, and exposure systems |
| Manual ITSM ticket process | Familiar governance and assignment | Requires users to discover and transpose technical context before work can start |
| Data warehouse / BI reporting | Broad analytics and historical reporting | Usually lacks near-real-time operational interaction and approval-gated remediation |
| General workflow or SOAR automation | Powerful orchestration | Can be expensive or overly broad for targeted endpoint reconciliation; requires careful human review |

### Differentiators for MVP

1. **Evidence-first reconciliation:** each conclusion points to source, source record, retrieval time, and confidence.
2. **Collaborative live canvas:** check state, assignments, notes, cleanup state, and history are server-authoritative and shared.
3. **Dual execution engine:** conversational affordance for small requests and deterministic, parallel Python execution for batch work.
4. **Human-governed dispatch:** the product prepares and executes only explicitly approved, allowlisted actions.
5. **Operational continuity:** actions and exports work with the systems customers already use rather than requiring replacement.

## 8. MVP Market Requirements

### Must Have

- Read-only evidence collection from ServiceNow, Cortex XDR, Jamf Pro, Microsoft Intune, and Tenable, including source status and timestamp.
- Input through conversational text, pasted usernames, and CSV upload.
- Deterministic skill bind after sanitization: a pasted name list or any CSV uses host-invoked `asset-ops` scripts; a single serial/hostname/user uses `device-lookup` MCP. Instruction prose is not counted as an identity.
- Shared workspace dashboard with filters, device/user evidence, notes, check state, assignment, CMDB cleanup state, activity history, and CSV export.
- Structured discrepancy analysis with evidence IDs, confidence, and recommended playbook.
- Approval-gated ServiceNow ticket creation and Jamf policy dispatch for allowlisted actions only.
- Workspace boundaries, one operational user role, administrator-only configuration, immutable audit history, and secret redaction.

### Should Have During Pilot

- Connector-health visibility and partial-result handling.
- Batch progress, safe retry, and per-connector rate-limit controls.
- Measurement dashboards for routing, investigation time, closure, action safety, and evidence coverage.
- Configurable action expiration and bulk-target limits.

### Explicitly Not in MVP

- Autonomous remediation without an explicit approval record.
- Automatic CMDB deletion or full bidirectional synchronization.
- Replacement consoles for the integrated vendors.
- Support for additional connector families before validating the initial five.
- Broad, free-form agent authority to mutate endpoint or CMDB data.

## 9. Success Measures and Pilot Design

### Instrumented Product Measures

| Measure | Pilot Target / Decision Rule | Instrumentation |
| --- | --- | --- |
| Route correctness | 100% of accepted requests follow the documented threshold rule | Query-run mode, normalized input count, input type |
| Approval coverage | 100% of state-changing calls link to an unexpired approval and audit event | Action request, approval, execution receipt |
| Collaboration latency | 99.9% of accepted canvas mutations visible to active collaborators in 5 seconds or less | Server event and client-ack timestamps |
| Evidence coverage | Establish baseline; investigate any run with missing source status | Per-device connector result, retrieval time, error state |
| Investigation cycle time | Reduce median time against the customer's pre-pilot baseline | Request accepted, decision recorded, work item closed |
| CMDB discrepancy closure | Improve closure rate and reduce aging against baseline | Cleanup state transitions and timestamps |
| User trust | At least 80% of pilot respondents find evidence and next action useful | In-product survey after completed runs |

### Pilot Exit Criteria

1. At least one recurring reconciliation workflow is completed end to end with real, approved connector data.
2. The team can explain source provenance for every displayed conclusion and inspect partial-failure state.
3. All tested remediation attempts have complete scope, approval, and receipt records.
4. The product demonstrates a measurable improvement or a credible baseline for investigation time and backlog closure.
5. No unresolved critical security finding permits cross-workspace data access, secret exposure, or approval bypass.

## 10. Risks and Product Guardrails

| Risk | Product Requirement / Guardrail |
| --- | --- |
| Conflicting or stale source data | Display source and retrieval time; retain confidence; label insufficient evidence rather than inventing a conclusion. |
| Incorrect identity correlation | Use explicit matching confidence and review path; do not silently merge ambiguous devices. |
| Unsafe automated action | Separate recommendation, action request, approval, and execution; use allowlists, expiration, target limits, and idempotency. |
| LLM overreach or data leakage | Supply normalized/redacted evidence only; constrain outputs to a schema; prohibit model access to secrets and direct mutations. |
| API rate limits and partial outages | Queue batch work, obey connector-specific limits, report source-level failure, and preserve successful evidence. |
| Low adoption because existing tools remain primary | Integrate with existing evidence and ticket workflows; avoid forcing a replacement console. |

## Open Questions

- Which persona owns the purchase and the pilot operating budget?
- Which reconciliation workflow has enough frequency, volume, and existing baseline data to be the first design-partner use case?
- What source precedence and freshness policy governs a disagreement between CMDB, MDM, EDR, and vulnerability data?
- Which ServiceNow ticket fields and Jamf policies are allowlisted for the first pilot?
- What identity provider, role model, audit retention period, data residency, and concurrency targets apply?
- Are Cortex XDR and Tenable API permissions already available through an internal integration platform?

## Sources

- Product brief supplied by the requestor on 2026-08-26.
- [Microsoft Intune device compliance policies](https://learn.microsoft.com/en-us/intune/intune-service/protect/device-compliance-get-started), accessed 2026-08-26.
- [Jamf product documentation](https://www.jamf.com/resources/product-documentation/), accessed 2026-08-26.
- [Palo Alto Networks Cortex documentation](https://cortex-docs.paloaltonetworks.com/), accessed 2026-08-26.
- [Tenable documentation](https://docs.tenable.com/), accessed 2026-08-26.
- [ServiceNow CMDB overview](https://www.servicenow.com/products/itsm/what-is-cmdb.html), accessed 2026-08-26. Page content was not extractable during this research pass; it is retained as the vendor reference rather than support for an unverified claim.
- [Fleet Recon PRD](prd.md).
- [AAMAD configuration](../../aamad.config.yml).

## Assumptions

- Fleet Recon is initially an internal or design-partner enterprise product, not a broadly self-serve SaaS offering.
- Named integrations offer approved API access appropriate to the narrowly defined MVP operations.
- The selected Claude Agent SDK session host will support constrained orchestration but will not be an authority for direct state change. CrewAI remains Future Work.
- The PRD remains the engineering contract; this MRD drives market, buyer, and outcome prioritization.

## Audit

- 2026-08-26 | product-mgr | Rewrote MRD after research review. Replaced an accidental Project Manager-authored feature summary with a market-focused document, cited primary vendor documentation, and labeled unvalidated commercial claims as pilot hypotheses.
- 2026-08-29 | system-arch | Aligned dual-engine threshold with requestor guidance: 1–4 micro-query, 5+ batch; identity lists excluded from model context.
- 2026-08-29 | system-arch | After skill-pack review: name lists use `asset-ops` scripts at any size; MCP is `device-lookup` for one identifier.
