# Fleet Recon Phase 1 Execution Plan

## Objective

Produce a build-ready, testable MVP backlog from the MRD and PRD. Work is prioritized to establish secure, observable foundations before connector breadth and automated action.

## Priority Backlog

### Epic 1: Product and Architecture Baseline

**Outcome:** Architecture, security boundaries, and operational decisions are ready for implementation.

| ID | User Story | Acceptance Criteria | Priority |
| --- | --- | --- | --- |
| FR-ARCH-01 | As an engineering team, we need a SAD that selects the web, persistence, queue, real-time, and identity components so implementation has clear boundaries. | SAD maps every PRD functional requirement to an owning service and records deployment, data flow, and failure decisions. | P0 |
| FR-ARCH-02 | As a security reviewer, I need connector credential and authorization boundaries defined so secrets and actions are protected. | Threat model identifies secret storage, role checks, audit data, tenancy, and approval boundary mitigations. | P0 |
| FR-ARCH-03 | As an operator, I need an observable system so I can diagnose run, connector, and action failures. | Structured log, metric, trace, correlation-ID, and alert requirements are documented. | P0 |

### Epic 2: Workspace, Identity, and Live State Foundation

**Outcome:** Authorized users can enter a workspace and collaboratively view durable state.

| ID | User Story | Acceptance Criteria | Priority |
| --- | --- | --- | --- |
| FR-CORE-01 | As a user, I need authenticated workspace access so my data and actions are correctly scoped. | One operational user role has the documented MVP capabilities; connector configuration and action allowlists are restricted to the designated administrator. | P0 |
| FR-CORE-02 | As an operator, I need a persistent query-run and evidence model so investigation history survives refreshes. | Core entities from PRD section 5 persist with migration, validation, and audit events. | P0 |
| FR-CORE-03 | As collaborators, we need timely shared work-item changes. | Check, assignment, note, and cleanup-state updates broadcast within five seconds; stale version writes conflict safely. | P0 |
| FR-CORE-04 | As an operator, I need filters and export so I can focus and hand off results. | Filtered results export CSV with data-source timestamps. | P1 |

### Epic 3: Intake and Deterministic Dual-Engine Execution

**Outcome:** Requests are safely normalized and the execution engine selects the right route every time.

| ID | User Story | Acceptance Criteria | Priority |
| --- | --- | --- | --- |
| FR-ROUTE-01 | As an operator, I can paste usernames or upload a CSV for investigation. | Input validation, sanitization, deduplication, rejection feedback, and upload constraints are implemented. | P0 |
| FR-ROUTE-02 | As the platform, I must route small and large requests predictably. | 1-4 normalized identities use micro-query; >4 or CSV uses batch; instruction prose is stripped; decision is persisted and fully unit-tested. | P0 |
| FR-ROUTE-03 | As an operator, I need batch work that progresses without blocking the UI. | A durable job creates internal CSV payload reference, follows rate limits, supports safe retry, and emits progress events. | P0 |
| FR-ROUTE-04 | As an operator, I need clear in-chat status and a spreadsheet-ready result. | Chat streams permitted micro-query cards, batch status, partial failures, correlation ID, and a Slack-style CSV artifact (preview, copy, download). | P0 |

### Epic 4: Connector Contract and Read-Only Evidence

**Outcome:** The platform collects reliable, provenance-preserving evidence from all five systems.

| ID | User Story | Acceptance Criteria | Priority |
| --- | --- | --- | --- |
| FR-CONN-01 | As an administrator, I can validate and monitor connector configuration. | Connection tests, health status, secret references, and least-privilege scopes are available without exposing secrets. | P0 |
| FR-CONN-02 | As an operator, I can see ServiceNow CMDB and ownership evidence. | Normalized ServiceNow adapter includes source IDs and retrieval/error status. | P0 |
| FR-CONN-03 | As an operator, I can see Cortex XDR active telemetry and OS classification. | Normalized Cortex adapter supports identity lookup and provenance. | P0 |
| FR-CONN-04 | As an operator, I can see Jamf and Intune management/compliance evidence. | macOS and Windows adapters support independent partial failure and shared device correlation. | P0 |
| FR-CONN-05 | As an operator, I can see Tenable exposure and last scan state. | Normalized Tenable adapter returns approved finding fields and provenance. | P1 |

### Epic 5: Collaborative Canvas and Agent Analysis

**Outcome:** Teams can make and share evidence-based work decisions.

| ID | User Story | Acceptance Criteria | Priority |
| --- | --- | --- | --- |
| FR-CANVAS-01 | As an operator, I can inspect users, devices, source evidence, and findings in one canvas. | Layout supports specified filters, tables, drill-down, and source/error visibility. | P0 |
| FR-AGENT-01 | As an operator, I receive evidence-backed discrepancy findings. | Analysis agent emits schema-valid categories, confidence, cited evidence IDs, and playbook; insufficient evidence is explicit. | P0 |
| FR-CANVAS-02 | As a team member, I can annotate, assign, and track CMDB cleanup. | Work-item controls respect permissions, preserve versions, and create activity entries. | P0 |

### Epic 6: Approval-Gated Dispatch

**Outcome:** Selected work is converted into safe, auditable actions.

| ID | User Story | Acceptance Criteria | Priority |
| --- | --- | --- | --- |
| FR-ACT-01 | As an operator, I can request a scoped remediation or ticket action from selected work items. | Request preview includes target scope, rationale, connector, parameters, expiration, and idempotency key. | P0 |
| FR-ACT-02 | As a user, I can confirm or cancel a scoped action in chat and canvas. | Confirmation is authenticated, durable, visible in both surfaces, and required before execution. | P0 |
| FR-ACT-03 | As an operator, I can create ServiceNow tickets from confirmed requests. | Only administrator-allowlisted ticket operations execute and produce receipt/audit records. | P1 |
| FR-ACT-04 | As an operator, I can trigger confirmed Jamf policies. | Only administrator-allowlisted policies execute exactly once per idempotency key and report per-target outcome. | P1 |

### Epic 7: Quality, Security, and Pilot Readiness

**Outcome:** The MVP is safe and measurable enough for a controlled pilot.

| ID | User Story | Acceptance Criteria | Priority |
| --- | --- | --- | --- |
| FR-QUAL-01 | As a maintainer, I need automated coverage of critical behavior. | Unit and integration suites cover all PRD acceptance criteria and connector contracts. | P0 |
| FR-SEC-01 | As a security reviewer, I need the MVP assessed before delivery. | Security assessment covers auth, secrets, injection, upload, prompt/data exposure, approval bypass, and dependencies. | P0 |
| FR-OPS-01 | As an operations manager, I need pilot success data. | Dashboard or queryable metrics track MRD success metrics, routing, failures, and action outcomes. | P1 |
| FR-REL-01 | As a pilot operator, I need delivery guidance. | Deployment runbook, rollback path, connector onboarding, and user guide are complete. | P1 |

## Delivery Sequence

1. Complete Epic 1 and the P0 stories of Epic 2.
2. Build Epic 3 routing and execution backbone before adding connector fan-out.
3. Implement connector contract and ServiceNow/Cortex first; add Jamf, Intune, then Tenable with contract tests.
4. Deliver canvas work state and analysis against persisted evidence.
5. Add approval boundary before implementing any state-changing connector.
6. Complete quality/security gates, then run a controlled pilot with representative batches.

## Dependencies and Risks

| Dependency / Risk | Impact | Mitigation |
| --- | --- | --- |
| Integration credentials, API scopes, and rate limits unavailable | Blocks connector validation | Confirm account ownership and sandbox access during architecture phase. |
| Source identity fields disagree | Can create incorrect device correlation | Maintain confidence/provenance, require review for ambiguous joins, and establish source precedence in SAD. |
| Real-time event delivery is unreliable | Team state becomes misleading | Use server-authoritative versions, reconnect synchronization, and activity audit trail. |
| Model hallucination or overreach | Unsafe recommendations/actions | Schema-constrained outputs, evidence citation, tool restrictions, approval gates, and allowlists. |
| Broad remediation selection | High operational blast radius | Show target count and impact preview; enforce configurable approval limits and expiration. |

## Handoff

- `@system.arch`: produce SAD and SFS using [prd.md](prd.md), resolving data model, deployment, connector, security, and real-time choices.
- `@project.mgr`: prepare only the selected project skeleton, dependency manifest, and environment templates after SAD approval.
- Build personas: implement epics in the sequence above, recording traceability to story IDs.

## Sources

- [mrd.md](mrd.md).
- [prd.md](prd.md).
- [aamad.config.yml](../../aamad.config.yml).

## Assumptions

- Product owner prioritizes a controlled pilot over broad connector/action coverage when tradeoffs arise.
- The architecture phase will split epic stories into implementation tasks without changing acceptance criteria.

## Open Questions

- Which connector should be treated as the first integration vertical for pilot validation?
- Is ServiceNow ticket creation sufficient as the first action, or must Jamf dispatch be included in the pilot?
- Who is authorized to approve actions and configure connector allowlists?

## Audit

- 2026-08-26 | product-mgr | Created prioritized MVP execution plan from MRD and PRD.
- 2026-08-29 | system-arch | Raised FR-ROUTE-04 to P0; aligned FR-ROUTE-02 with 4-identity threshold and chat CSV artifact.