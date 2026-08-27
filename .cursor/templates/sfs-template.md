# AAMAD System Functional Specification (SFS) Template

## Context & Instructions
Generate a System Functional Specification for a single feature or user story.
Base all content on the PRD, SAD, and the referenced user story. Do not invent requirements.
Record the selected runtime (`AAMAD_TARGET_RUNTIME`) when the feature touches agent or API behavior.

## Input Requirements

**PRD Document**: [REFERENCE OR PASTE RELEVANT PRD SECTIONS]
**User Story / Feature ID**: [e.g. US-001 or feature-id]
**Selected Runtime**: [crewai | claude-agent-sdk | cursor-sdk | N/A for pure UI]

## SFS Structure — Generate All Sections Below

### 1. Purpose and Scope

- **Feature ID**: Unique identifier matching PRD or user-story ID
- **Purpose**: What this feature accomplishes for the user
- **In Scope**: Behaviors covered by this SFS
- **Out of Scope**: Explicit exclusions deferred to other features or Future Work

### 2. Traceability

- **PRD Anchors**: Section or requirement IDs
- **User Story**: Link to `project-context/1.define/user-stories/<id>.md`
- **SAD Anchors**: Relevant architectural views or decisions

### 3. Inputs

- **Input Name**: Description, type/format, source, validation rules
- List every required and optional input

### 4. Processing Behavior

- Step-by-step processing description
- Runtime-agent or API involvement when applicable
- State changes and side effects

### 5. Outputs

- **Output Name**: Description, type/format, destination
- Success response shape (schema-level, not full payload examples unless required)

### 6. Validations and Constraints

- Input validation rules
- Business rules and invariants
- Timing, rate, or size constraints when known

### 7. Error Handling and Exceptions

- Expected failure modes and user-visible or API error envelopes
- Retry, fallback, or halt behavior aligned with the selected runtime adapter

### 8. Acceptance Criteria

- Testable conditions derived from the user story
- Mapping notes for QA (`*test-unit` / `*test-integration`)

## Sources

- List PRD/SAD/user-story paths and external references used

## Assumptions

- Document gaps filled by inference; do not present them as verified requirements

## Open Questions

- Unresolved items for stakeholder or architect resolution

## Audit

- Timestamp, persona id (`system-arch`), action (`create-sfs`), resolved `AAMAD_TARGET_RUNTIME` when applicable
