# AAMAD User Story Template

## Context & Instructions
Generate one user story per file under `project-context/1.define/user-stories/`.
Derive stories from the PRD and optional system description. Do not invent product scope.

## Input Requirements

**PRD Document**: [REFERENCE RELEVANT PRD SECTIONS]
**System Description** (optional): [REFERENCE IF PRESENT]
**Story ID**: [e.g. US-001]

## User Story Structure — Generate All Sections Below

### 1. Story Identity

- **ID**: US-NNN (stable identifier)
- **Title**: Short descriptive name
- **Priority**: Must / Should / Could (MVP focus: Must only unless justified)
- **Persona**: Primary user persona from PRD

### 2. Narrative

As a [persona], I want [capability], so that [outcome].

### 3. Acceptance Criteria

Numbered, testable criteria (Given / When / Then or bullet checklist).
Each criterion should be usable by QA for unit or integration test derivation.

### 4. Scope Notes

- **In Scope for MVP**: Behaviors included now
- **Deferred**: Explicit Future Work

### 5. Traceability

- **PRD Anchors**: Sections or requirement IDs
- **Related SFS**: `project-context/1.define/sfs/<feature-id>.md` when created

## Sources

- PRD / system-description paths used

## Assumptions

- Gaps filled by inference

## Open Questions

- Items needing clarification before architecture or build

## Audit

- Timestamp, persona id (`product-mgr`), action (`create-stories`)
