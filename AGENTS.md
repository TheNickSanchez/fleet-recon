# AAMAD Agent Framework

This project uses the AAMAD framework for multi-agent development.
Framework version: 0.7.5
See the full agent definitions in the IDE-specific directories.

## Agent Personas
- **@product-mgr** — Product Manager: Orchestrates product vision and requirements
- **@system.arch** — System Architect: Produces SAD and SFS documents
- **@project.mgr** — Project Manager: Scaffolds project and environment
- **@frontend.eng** — Frontend Developer: Builds MVP chat interface
- **@backend.eng** — Backend Developer: Builds backend for the selected runtime
- **@integration.eng** — Integration Engineer: Connects frontend and backend
- **@qa.eng** — QA Engineer: Validates MVP functionality (unit + integration)
- **@security.eng** — Security Engineer: Assesses MVP security before Deliver
- **@devops.eng** — DevOps Engineer: Packages deploy/CI, runbook, and user guide

## Workflow
1. **Define** (Phase 1): @product-mgr → elicitation → Market Research (optional) → PRD → @system.arch → SAD
2. **Build** (Phase 2): @project.mgr → @frontend.eng / @backend.eng → @integration.eng → @qa.eng → @security.eng
3. **Deliver** (Phase 3): @devops.eng → deploy.md + user-guide.md

## Rules
All development follows AAMAD core rules. See project-context/ for artifacts.
Run `aamad validate` to check artifact quality gates.

## Agent Definitions
See `.github/agents/` for VS Code / GitHub Copilot agent definitions.
