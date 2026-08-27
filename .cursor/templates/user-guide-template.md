# AAMAD User Guide Template

## Context & Instructions
Generate an installation guide and end-user manual from project artifacts.
Derive content from `setup.md`, `integration.md`, `deploy.md`, and the PRD. Do not invent product capabilities that are not implemented.

## Input Requirements

**PRD**: [REFERENCE `project-context/1.define/prd.md`]  
**setup.md**: [REFERENCE]  
**integration.md**: [REFERENCE]  
**deploy.md**: [REFERENCE]  
**security.md** (optional): [REFERENCE]

## User Guide Structure — Generate All Sections Below

### 1. Product Overview

- What the product does (1–2 paragraphs)
- Who it is for
- MVP limitations / known gaps

### 2. Prerequisites

- Runtime, OS, accounts, and API keys (env var **names** only)
- Supported browsers or clients

### 3. Installation

- Local install steps from setup.md
- Configuration (including `aamad.config.yml` / `.env.example` keys when relevant)
- Verify health / smoke check

### 4. Getting Started

- First-run walkthrough of the primary MVP flow (e.g. chat)
- Screenshots placeholders only if needed (describe UI, do not fabricate images)

### 5. Everyday Use

- Common tasks and expected outcomes
- How to interpret agent responses / errors

### 6. Troubleshooting

- Common failures and remediations from integration.md / qa.md / deploy.md
- Where to find logs

### 7. Deployment Notes (operators)

- Summary pointer to deploy.md runbook
- Rollback overview (high level)

## Sources

- Artifact paths used

## Assumptions

- Environment assumptions not verified at write time

## Open Questions

- Gaps in operator docs

## Audit

- Timestamp, persona id (`devops-eng`), action (`document-user-guide`), resolved `AAMAD_TARGET_RUNTIME`
