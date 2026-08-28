# Fleet Recon Frontend Implementation

## Scope

React 19 + TypeScript + Vite frontend for the Fleet Recon MVP, implementing SAD §3 (Frontend Architecture Specification).

The original request used the label "recruitment assistant", which conflicts with the PRD/SAD and backend scope. This implementation follows the authoritative Fleet Recon endpoint-reconciliation product scope, consistent with the resolution recorded in `backend.md`.

This document supersedes the first-pass implementation. That pass was functional but visually and interactionally weak: a `+` menu that offered "Paste Usernames" as a discrete mode, a permanently mounted canvas panel that consumed a third of the viewport while empty, no navigation model, and inline error blocks. The interface was rebuilt around an explicit design system, a collapsible navigation rail, and intent-detecting input.

## Interaction Design Decisions

| Decision | Rationale |
| --- | --- |
| **Input kind is inferred, never selected.** | Pasting is a gesture, not a mode. `parseInput()` mirrors the server sanitizer and classifies `typed` vs `pasted` from separators and token count, so the user just types or pastes and presses Enter. |
| **The `+` menu holds only real affordances.** | It now contains CSV upload plus the two allowlisted integration actions (disabled with a reason until canvas rows are selected). Nothing in it duplicates what typing already does. |
| **Canvas is opt-in and never renders empty chrome.** | The side panel is closed by default, opens automatically when a run produces rows, and is toggleable with `⌘\`. When it has no rows it explains what puts rows there instead of showing an empty frame. |
| **Collapsible navigation rail.** | Persistent left navigation collapses to a 60 px icon rail (`⌘B`, persisted). Administration section only renders for the administrator claim. Below 900 px it becomes an overlay drawer. |
| **Live parse feedback in the composer.** | Detected username count, routing mode (`Micro-query` / `Batch automation`), and ignored-token count update as the user types, so routing behaviour is visible *before* submission. |
| **Errors surface as toasts, not inline blocks.** | Transient failures use a toast queue. Persistent conditions (authorization denial, backend gap) render as in-place notices with a stated remedy. |
| **Honest empty and stalled states.** | The backend has no orchestration worker, so runs remain `queued`. Rather than spinning forever, polling stops after 30 s and the run card explains exactly why results are pending. |
| **Command palette (`⌘K`).** | Single entry point for navigation, canvas/sidebar toggles, theme, and role switching. |
| **Light and dark themes.** | System-following by default, overridable, persisted. All colour decisions come from tokens, so both themes stay in sync. |

## Design System

`src/styles/tokens.css` is the single source of truth for colour, type scale, spacing (4 pt), radii, elevation, motion, and z-index. `src/styles/base.css` provides the reset plus shared primitives (`btn`, `input`, `select`, `switch`, `card`, `badge`, `table`, `empty`, `skeleton`, `kbd`).

Both themes are defined as token overrides on `[data-theme]`, so no component stylesheet contains a literal colour. Feature stylesheets are colocated with their components and consume tokens only.

> **Note:** `src/main.tsx` imports `tokens.css` and `base.css` *before* any feature module. CSS ordering matters here — Vite emits stylesheets in import-evaluation order, and base primitives share single-class specificity with component rules, so importing them last silently overrode component styling.

## Routes & Screens

Routing uses `react-router-dom` with deep-linkable paths per SAD §3.2.

| Route | Screen | Access |
| --- | --- | --- |
| `/workspaces/:id` | Copilot Chat with optional canvas side panel | Workspace User |
| `/workspaces/:id/canvas` | Full-width Live Canvas | Workspace User |
| `/workspaces/:id/activity` | Session activity timeline | Workspace User |
| `/workspaces/:id/settings/tools` | Tool configuration | Administrator |
| `/workspaces/:id/settings/actions` | Action request lifecycle | Administrator |
| `/workspaces/:id/settings/credentials` | Credential management (inert — no endpoint) | Administrator |
| `/workspaces/:id/settings/health` | Live API probes | Administrator |

Administration routes redirect to chat when the client-side role is not administrator. This is UX filtering only; the server enforces authorization on every request.

## Delivered Features

**Copilot Chat** (`src/features/chat/`)
- Auto-growing composer; `Enter` sends, `Shift`+`Enter` inserts a newline.
- Live parse preview (accepted / ignored / routing mode).
- CSV upload via the `+` menu or drag-and-drop, validated client-side against the server's `.csv` and 5 MiB constraints before upload.
- Message timeline with user bubbles and agent run cards showing status, mode, accepted/rejected counts, run ID, correlation ID, and copy-to-clipboard for support.
- Suggestion cards on the empty state that seed the composer with representative inputs (single, cohort, batch).

**Live Canvas** (`src/features/canvas/`)
- Rows derived from every accepted identifier in a run, filterable by username, status, and run.
- Multi-select with a selection action bar that creates a scoped action request.
- CSV export of the current filtered view.
- Renders as a compact side panel next to chat and as a full-width, centre-constrained page.

**Action Requests** (`src/features/actions/`)
- Creation dialog restricted to the server's allowlisted `(connector, operation)` pairs, with an explicit target preview and expiry statement.
- Lifecycle view with a three-step progress indicator, live expiry countdown, and controls gated on real state (`pending_confirmation` → `confirmed` → `executed`).

**Tools** (`src/features/settings/ToolsView.tsx`)
- Table of tool definitions with integration, assigned agents, parameter summary, enabled state, and configuration version.
- Editor dialog with an enable switch, agent chips, JSON parameter editing with parse validation, and a dirty-state warning naming the resulting version.
- HTTP 409 conflicts reload authoritative server state and inform the user rather than silently discarding the edit.

**Health** (`src/features/settings/HealthView.tsx`)
- Live probes against `GET /health` and `GET /ready` with measured round-trip latency. This screen shows real data, not a placeholder.

**Activity** (`src/features/activity/`)
- Reconstructed timeline of runs and action transitions with actor and correlation metadata, explicitly labelled as browser-session state rather than a server audit log.

## Deliberately Inert

`CredentialsView` is presented as a documented gap, not a mock. The MVP API exposes no `/admin/credentials` route; building a form that appears to store secrets and does not would be worse than showing nothing. The view states the missing endpoint and lists the requirements the real implementation must satisfy (write-only secret inputs, alias/status metadata, credential version, server-side authorization).

Connector-level diagnostics on the Health screen are handled the same way.

## API Integration

`src/api/client.ts` wraps every endpoint the backend serves:

| Method | Endpoint |
| --- | --- |
| `GET` | `/health`, `/ready` |
| `POST` | `/workspaces/{id}/runs`, `/workspaces/{id}/runs/upload` |
| `GET` | `/workspaces/{id}/runs/{runId}` |
| `GET` / `PATCH` | `/workspaces/{id}/admin/tools[/{toolId}]` |
| `POST` | `/workspaces/{id}/action-requests[/{actionId}/confirm|/execute]` |

Error handling normalises both FastAPI's `{ detail }` shape (including 422 validation arrays) and the project's `{ error, correlation_id }` envelope into a typed `ApiError` carrying `status` and `correlationId`. Network failures produce an actionable message naming the target URL.

**Corrected contract mismatches from the first pass:**
- `ToolConfigView.assigned_agents` is `string[]`. Python's `set[str]` serialises to a JSON array; the previous `Set<string>` typing was wrong and `Array.from()` on a plain array silently produced empty output.
- Action requests are created as `pending_confirmation`, not `pending`. The previous confirm button was gated on a status the server never emits, so confirmation was unreachable through the UI.
- The action operation form is constrained to `ALLOWED_ACTIONS`; free-text operations were rejected with 422.

## CORS and the Dev Proxy

The backend registers no CORS middleware, so a browser at `http://localhost:5173` calling `http://localhost:8000` is blocked by the same-origin policy. The first pass was validated with `curl`, which does not enforce CORS, so this never surfaced.

`vite.config.ts` now proxies `/api` to `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8000`), and `VITE_API_BASE_URL` defaults to the relative `/api/v1`. The browser only ever talks to its own origin. Pointing `VITE_API_BASE_URL` at an absolute URL remains supported for a CORS-enabled deployment.

## Runtime Controls

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | API base path used by the browser |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Dev-server proxy target |
| `VITE_PORT` | `5173` | Dev/preview server port |
| `VITE_DEV_ROLE` | `workspace_user` | Initial simulated role |
| `VITE_DEV_ACTOR_ID` | `local-dev-user` | `X-Actor-Id` header value |
| `VITE_WORKSPACE_ID` | `550e8400-…0000` | Workspace opened by default |

The simulated role is persisted and applied synchronously at module load, so the first request a component issues already carries the correct `X-Role`. (An effect-based approach raced with child data-loading effects and produced a spurious 403 on the Tools screen.)

## Directory Structure

```text
frontend/src/
  app/          App.tsx, SessionContext.tsx, Sidebar.tsx, TopBar.tsx, AppShell.css
  components/   Icon, Menu, Modal, Toast, CommandPalette (+ styles)
  features/
    chat/       ChatView, Composer, Message, parseInput
    canvas/     CanvasPanel
    actions/    ActionsView, ActionRequestDialog
    activity/   ActivityView
    settings/   ToolsView, CredentialsView, HealthView
  hooks/        usePersistentState (+ useHotkey, useMediaQuery), useRunStatus
  api/          client.ts
  types/        api.ts
  lib/          uuid.ts
  styles/       tokens.css, base.css
```

## Accessibility

- Full keyboard operation: `⌘K` palette, `⌘B` navigation, `⌘\` canvas, `Enter`/`Shift`+`Enter` in the composer, arrow-key navigation and `Escape` dismissal in palette, menus, and dialogs.
- Visible focus rings on every interactive element via a global `:focus-visible` rule.
- Semantic landmarks and table headers; `aria-label` on icon-only controls; `aria-pressed` on toggles; `aria-selected` on palette options.
- `role="status"` live regions for run progress and toasts.
- Status is never conveyed by colour alone — every badge pairs colour with a label, and several add a dot or icon.
- `prefers-reduced-motion` disables animation globally.
- Both themes use tokens chosen for contrast against their surfaces.

## Known Gaps

| Gap | Cause | Handling |
| --- | --- | --- |
| Runs never leave `queued` | No orchestration worker in the MVP backend | Polling stops after 30 s; the run card explains why |
| No server-side canvas work items | `CanvasWorkItem` not persisted | Rows derived from submitted input; provisional client IDs, disclosed in the action dialog |
| No SSE or WebSocket | Not implemented server-side | Bounded polling via React Query |
| No credential endpoints | Not implemented server-side | View is inert and documents the requirement |
| No connector diagnostics | Not implemented server-side | Health shows real API probes only |
| No run/action list endpoints | Not implemented server-side | History persisted per browser in `localStorage` |
| Dev header identity | No OIDC integration yet | Clearly labelled `DEV IDENTITY`; server still authoritative |
| No automated tests | Out of MVP scope | Verified by typecheck, lint, build, and scripted browser walkthrough |

## Validation

- `npx tsc -b` — clean.
- `npm run lint` (oxlint) — 0 errors, 11 warnings, all `set-state-in-effect` on legitimate async-load effects or `only-export-components` fast-refresh advisories.
- `npm run build` — succeeds; ~330 kB JS (101 kB gzip), ~46 kB CSS (8.5 kB gzip).
- Scripted headless-Chromium walkthrough against the live backend covering: empty state, suggestion seeding, micro-query submission, batch submission, run polling, sidebar collapse, command palette, full-page canvas, row selection, action dialog, tools list, tool editor, health probes, activity, action requests, and mobile drawer — **no console or page errors**.
- Role authorization verified in-browser: Tools returns data as administrator and a handled 403 notice as workspace user.

## Development Workflow

```bash
# Terminal 1
cd backend && uv run uvicorn backend.main:app --reload --port 8000

# Terminal 2
cd frontend && npm install && cp .env.example .env.local && npm run dev
# http://localhost:5173
```

Switch roles from the account menu in the top bar, or with `⌘K` → "Switch role to Administrator".

## Assumptions

1. The authoritative product scope is Fleet Recon per PRD/SAD; "recruitment assistant" was a copy-paste error.
2. Backend behaviour is taken from `backend/main.py`, `backend/services.py`, and `backend/schemas.py` as the contract of record where documentation and code diverge.
3. Deriving canvas rows from submitted input is an acceptable MVP stand-in for server-side work items, given it is disclosed in the UI.
4. Persisting thread and canvas state in `localStorage` is acceptable because no list endpoints exist; it is per-browser and not shared collaboration state.
5. Bounded polling is an acceptable interim for SSE/WebSocket at MVP scale.
6. Plain CSS with a token layer is preferred over a component library for a small surface with a specific visual identity.
7. The Vite dev proxy is the correct place to resolve CORS, since modifying backend middleware is outside this persona's scope.

## Open Questions

1. Should `CanvasWorkItem` IDs be minted server-side on run creation so action requests target durable entities? (Blocks real remediation.)
2. Will run progress use SSE, WebSocket, or both? The canvas needs workspace-scoped events; chat needs run-scoped streaming.
3. Should CORS middleware be added to the backend, or is a same-origin reverse proxy the intended deployment topology?
4. What is the authoritative agent list for tool assignment? The editor currently offers `orchestrator`, `analysis`, and `dispatch` inferred from seed data.
5. Should the activity timeline be replaced by a server-side audit query endpoint before Deliver?
6. Is a shared design-token package needed if other Fleet Recon surfaces are built later?

## Sources

- `project-context/1.define/prd.md` — product scope, user flows, FR-1 through FR-9.
- `project-context/1.define/sad.md` — SAD §3 Frontend Architecture Specification, §3.2 structure, §3.3 interface requirements.
- `project-context/2.build/backend.md` — backend endpoints, runtime controls, known gaps.
- `backend/main.py`, `backend/services.py`, `backend/schemas.py` — authoritative API behaviour, status vocabulary, and validation limits.
- [React](https://react.dev), [Vite](https://vite.dev), [TanStack Query](https://tanstack.com/query), [React Router](https://reactrouter.com)

## Audit

- **2026-08-27, 16:00–16:45 UTC** | `@frontend.eng` | `*develop-fe`, `*add-placeholders`, `*style-ui`, `*document-frontend`
  - Initial implementation: Vite scaffold, chat composer, run polling, admin tool management, action request flow, placeholder screens, plain-CSS styling, typed API client.

- **2026-08-27, 23:15–00:15 UTC** | `@frontend.eng` | `*develop-fe`, `*style-ui`, `*document-frontend`
  - Rebuilt the interface after operator feedback that the first pass was amateurish.
  - Added `styles/tokens.css` and `styles/base.css` design system with light/dark themes.
  - Replaced the header-only layout with a collapsible navigation rail, top bar, mobile drawer, and `react-router-dom` routing per SAD §3.2.
  - Removed the "Paste Usernames" menu item; input kind is now inferred by `parseInput()` with live composer feedback.
  - Made the canvas opt-in, auto-opening on first result, with filters, multi-select, and CSV export.
  - Added toast notifications, command palette, modal system, and keyboard shortcuts.
  - Rewrote Health against live `/health` and `/ready`; kept Credentials deliberately inert with documented requirements.
  - Fixed contract defects: `assigned_agents` array typing, `pending_confirmation` status, allowlisted operations.
  - Fixed CSS import ordering, the dev-identity race producing a false 403, and added the Vite `/api` proxy to resolve the CORS blocker.
  - Verified with typecheck, lint, production build, and a scripted headless-browser walkthrough against the live backend.

## Next Steps

1. **Phase 2 Iteration 2** — server-side `CanvasWorkItem` persistence and workspace event delivery; replace derived rows and bounded polling.
2. **Phase 2 Iteration 3** — credential and connector-diagnostics endpoints; activate the two inert surfaces.
3. **Phase 3** — replace dev header identity with verified OIDC claims; decide the CORS/reverse-proxy topology for deployment.
4. **Testing** — component tests for `parseInput` and the action state machine; end-to-end coverage of the confirm/execute flow.
