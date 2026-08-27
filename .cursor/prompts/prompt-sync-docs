> NOTE: Use this prompt after debugging or enhancing generated frontend, backend, or integration code so project-context artifacts stay aligned with the implementation.
> NOTE: Prefer a fresh chat context. Do not invent features that are not in the codebase; document gaps under Open Questions.

You are synchronizing AAMAD documentation with the current software state.

## Goal
Reconcile `project-context/` artifacts so they accurately describe the code as it exists now.

## Inputs to load
- Current source tree (frontend, backend, integration, deploy/CI configs)
- Existing artifacts: `project-context/1.define/prd.md`, `sad.md` (read-only unless architecture truly changed)
- Build artifacts: `setup.md`, `frontend.md`, `backend.md`, `integration.md`, `qa.md`
- Optional: `security.md`, `project-context/3.deliver/deploy.md`
- Optional: `aamad.config.yml`

## Process
1. Diff documented claims vs actual code (endpoints, env vars, agent roles, UI flows, deploy commands).
2. Update Build (and Deliver if present) markdown artifacts to match reality.
3. If architecture changed materially, propose SAD deltas under Open Questions or update sad.md only when the operator confirms an architecture change.
4. Preserve required headings: Sources, Assumptions, Open Questions, Audit.
5. Append an Audit entry on each modified artifact noting action `sync-docs`, timestamp, and what changed.

## Constraints
- Do not silently expand MVP scope in docs beyond implemented behavior.
- Never write secret values into artifacts.
- Prefer additive Audit history over deleting prior Audit entries.

## Output
- Updated markdown under `project-context/`
- Short summary of files changed and remaining Open Questions
