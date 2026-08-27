# AAMAD System Description Template

## Context & Instructions
Capture a rich, structured project definition before MRD/PRD generation.
Prefer this document (or `*elicit-requirements`) when the use case is specialized, internal, or underspecified by a short prompt.
Do not invent facts; record unknowns under Open Questions.

## Input Requirements

**Working title**: [PROJECT NAME]  
**Author / stakeholder**: [NAME]  
**Selected Runtime** (optional at this stage): [crewai | claude-agent-sdk | cursor-sdk | undecided]

## System Description — Generate All Sections Below

### 1. Intent and Problem

- **Problem statement**: What problem does this system solve?
- **Primary users / operators**: Who uses it and in what setting?
- **Success definition**: What does "good enough for MVP" look like?

### 2. Domain Context

- Domain vocabulary and critical entities
- Existing systems, data sources, or workflows to respect
- Regulatory or organizational constraints (if any)

### 3. Functional Requirements

Numbered requirements with stable IDs (`FR-001`, …):

| ID | Description | Priority (Must/Should/Could) |
|----|-------------|------------------------------|
| FR-001 | … | Must |

### 4. Non-Functional Requirements

Numbered NFRs (`NFR-001`, …) covering performance, security, reliability, usability, and operability as applicable.

### 5. Constraints

- Technology constraints (language, cloud, offline, etc.)
- Budget / timeline constraints
- Integration constraints (must / must-not integrate with …)

### 6. Assumptions

- Explicit assumptions the build may rely on

### 7. Acceptance Criteria

Numbered criteria (`AC-001`, …) that QA can map to unit and integration tests.
Prefer Given/When/Then or checklist form.

### 8. Out of Scope / Future Work

- Explicit exclusions for MVP

## Sources

- Stakeholder interviews, notes, prior docs

## Assumptions

- Gaps filled by inference during elicitation

## Open Questions

- Items to resolve before or during PRD/SAD

## Audit

- Timestamp, persona id (`product-mgr`), action (`elicit-requirements`)
