# Fleet Recon Backend Implementation

## Scope

Implemented the initial Python backend for Fleet Recon, the endpoint-reconciliation workspace defined in the PRD and SAD.

## Delivered

- FastAPI application in `backend/main.py` with health, readiness, query-run, CSV upload, run lookup, administrator tool configuration, and confirmation-gated action-preview endpoints.
- Deterministic request intake: control-character removal, case-insensitive username deduplication, safe invalid-input rejection, and persisted micro-query/batch routing. Five or fewer unique non-CSV usernames route to `micro_query`; six or more, or all CSV uploads, route to `batch_automation`.
- In-memory MVP application service in `backend/services.py`, providing an intentionally replaceable repository boundary for query runs, approved tool configurations, and action requests.
- Three-role CrewAI Application Crew in `backend/agents/crew.py`, with all Agent and Task definitions externalized to version-controlled YAML under `backend/agents/config/`. It is sequential, has persistent memory disabled, uses explicit task context chaining, and limits iteration to 6/5/4 across Orchestrator, Analysis, and Dispatch roles.
- Role boundary: administrative tool catalog/configuration APIs require an Administrator identity. The current header-based identity adapter is development-only and must be replaced by OIDC validation before deployment.
- Confirmation boundary: only ServiceNow ticket creation and Jamf policy triggers are allowlisted. Execution is rejected until the exact action preview is confirmed and unexpired.
- Pytest API coverage for routing threshold, CSV routing, invalid input, Administrator-only tool access, and confirmation-gated action execution.
- `pyproject.toml` and `.env.example` with CrewAI/FastAPI dependencies and names-only integration configuration.

## API Surface

| Endpoint | Current behavior |
| --- | --- |
| `GET /api/v1/health`, `GET /api/v1/ready` | Liveness and local readiness. |
| `POST /workspaces/{workspace_id}/runs` | Validates typed/pasted usernames and creates a queued routed run. |
| `POST /workspaces/{workspace_id}/runs/upload` | Validates UTF-8 CSV upload and creates a batch run. |
| `GET /workspaces/{workspace_id}/runs/{run_id}` | Returns workspace-scoped run metadata. |
| `GET/PATCH /workspaces/{workspace_id}/admin/tools` | Lists or version-updates approved tool settings; Administrator-only. |
| `POST /workspaces/{workspace_id}/action-requests` | Creates an exact-scope allowlisted action preview. |
| `POST /workspaces/{workspace_id}/action-requests/{id}/confirm` | Records confirmation of a pending unexpired action. |
| `POST /workspaces/{workspace_id}/action-requests/{id}/execute` | Enforces confirmed/unexpired state before marking execution. |

All paths shown in this table are prefixed with `/api/v1`.

## Runtime Controls

- `AAMAD_TARGET_RUNTIME`: `crewai`, resolved from `aamad.config.yml`.
- Crew process: sequential; persistent memory: disabled; max RPM: 30.
- Crew role limits: Orchestrator 6 iterations, Analysis 5, Dispatch 4; each has a 60-second execution budget and two retries.
- Model configuration is supplied only through `CREWAI_MODEL_NAME` and `CREWAI_MODEL_API_KEY`. The current API uses deterministic domain services and does not invoke an LLM without an explicitly configured production execution path.

## Known Gaps

- PostgreSQL repositories, migrations, Redis/RQ jobs, object storage, SSE/WebSocket event delivery, and durable audit events are not yet implemented.
- OIDC claim validation, workspace membership lookup, API rate limiting, approved secret-manager integration, credential APIs, health checks, and the five live read connectors are deferred pending infrastructure and approved non-production credentials.
- Action execution currently validates policy state but does not call ServiceNow or Jamf; write adapters, receipts, idempotency acquisition, and audit persistence are required before any production mutation.
- The crew is defined and YAML-backed but intentionally is not kicked off from request handling until connector evidence and an approved model provider are configured. CrewAI remains orchestration support, never the authorization or action-policy authority.
- Canvas work-item, note, export, optimistic-concurrency, and collaboration endpoints are still pending their persistence/eventing implementation.

## Validation

- Focused API tests: `pytest tests/test_api.py`
- Local server after dependency installation: `uv run uvicorn backend.main:app --reload`

## Sources

- `project-context/1.define/prd.md`
- `project-context/1.define/sad.md`
- `.github/instructions/adapter-crewai.instructions.md`
- `aamad.config.yml`

## Assumptions

- The PRD/SAD's Fleet Recon endpoint-reconciliation requirements are authoritative over the request's alternate product name.
- A model provider, OIDC identity provider, PostgreSQL, Redis, object storage, and integration credentials will be supplied by later integration/deployment work.
- CrewAI's current ChromaDB dependency is incompatible with Python 3.14. The project pins local development to Python 3.12 and supports Python 3.11-3.13.

## Open Questions

1. Which approved model provider and model name should be used for production CrewAI task kickoff?
2. Which OIDC claims encode workspace membership and Administrator authorization?
3. Which secret manager and queue library are approved for the pilot deployment?
4. What ServiceNow ticket fields and Jamf policy IDs form the initial state-changing allowlist?

## Audit

- 2026-08-27 | `backend.eng` | `develop-be`, `define-agents`, `implement-endpoint`, `document-backend` | Resolved `AAMAD_TARGET_RUNTIME=crewai`; implemented initial FastAPI API, deterministic domain controls, YAML-backed CrewAI Application Crew, tests, and backend implementation record. Prompt traces are omitted because no production-facing CrewAI task execution is invoked in this scaffold.