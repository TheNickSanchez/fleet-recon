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

## Cursor Cloud specific instructions

Despite the top-level `README.md` claiming the project is "Define phase" with "no runnable application yet", the MVP is scaffolded and runnable. There are two services:

- **Backend** (`backend/`): FastAPI + CrewAI, Python 3.12, managed with `uv` (`pyproject.toml` + `uv.lock`). See `frontend/README.md` for the canonical run commands.
  - Run dev server: `uv run uvicorn backend.main:app --reload --port 8000`
  - Run tests: `uv run pytest`
  - Persistence is an in-memory MVP with no connector worker, so query runs intentionally stay `queued` and the canvas shows "Awaiting evidence" / "results pending". This is expected, not a bug.
  - Dev auth is header-based (`X-Actor-Id` / `X-Role`); no real OIDC. CrewAI/connector calls are disabled by default (`CREWAI_EXECUTE=false`), so no LLM or integration API keys are needed for local dev.
- **Frontend** (`frontend/`): React 19 + Vite + TypeScript, managed with `npm`. See `frontend/README.md` for the script table.
  - Copy `frontend/.env.example` to `frontend/.env.local` before `npm run dev` (git-ignored).
  - `npm run lint` (oxlint) emits `react(...)` warnings that are non-blocking and expected; it exits 0.
  - The Vite dev server binds to `localhost` only — reach it at `http://localhost:5173` (curling `http://127.0.0.1:5173` fails). It proxies `/api` to the backend at `127.0.0.1:8000`; the backend registers no CORS middleware, so keep requests same-origin (leave `VITE_API_BASE_URL=/api/v1`).

Run the backend before/alongside the frontend so the `/api` proxy resolves.
