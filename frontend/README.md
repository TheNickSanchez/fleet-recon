# Fleet Recon — Frontend

React 19 + TypeScript + Vite client for the Fleet Recon endpoint-reconciliation workspace.

## Quick start

```bash
# 1. Start the API (separate terminal, from the repository root)
cd backend && uv run uvicorn backend.main:app --reload --port 8000

# 2. Start the frontend
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open <http://localhost:5173>.

> The dev server proxies `/api` to the backend. The MVP API sends no CORS headers, so the
> browser must stay same-origin — keep `VITE_API_BASE_URL` as the relative `/api/v1` unless
> you are pointing at a CORS-enabled deployment.

## Scripts

| Command | Description |
| --- | --- |
| `npm run dev` | Dev server with HMR and the `/api` proxy |
| `npm run build` | Typecheck (`tsc -b`) then production build to `dist/` |
| `npm run preview` | Serve the production build with the same proxy |
| `npm run lint` | oxlint |

## Environment

Copy `.env.example` to `.env.local` and adjust. `.env.local` is git-ignored.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | API base path the browser calls |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Where the dev server forwards `/api` |
| `VITE_PORT` | `5173` | Dev/preview port |
| `VITE_DEV_ROLE` | `workspace_user` | Initial simulated role |
| `VITE_DEV_ACTOR_ID` | `local-dev-user` | `X-Actor-Id` header value |
| `VITE_WORKSPACE_ID` | `550e8400-…0000` | Workspace opened by default |

**The role switcher is a development affordance.** It sets the `X-Role` header the MVP backend
reads in place of verified OIDC claims. Hiding a route in the client is not an authorization
control — the server enforces access on every request. This must be replaced with a real token
exchange before any non-local deployment.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `⌘K` / `Ctrl+K` | Command palette |
| `⌘B` / `Ctrl+B` | Collapse or expand navigation |
| `⌘\` / `Ctrl+\` | Show or hide the canvas panel |
| `Enter` | Send the composer message |
| `Shift`+`Enter` | New line in the composer |
| `Esc` | Dismiss palette, menu, or dialog |

## Using it

1. **Paste or type usernames** in the composer. There is no mode to pick — the composer detects
   whether input is typed or pasted, shows how many identifiers it found, and previews whether the
   run routes to the micro-query or batch path.
2. **Upload a CSV** from the `+` menu or by dropping it on the composer. It needs a `username`
   column, at most 10,000 rows, and under 5 MiB.
3. **Work the canvas.** Accepted identifiers become rows. Filter them, select some, and choose
   *Request action* to create a scoped remediation request.
4. **Confirm and execute** from Administration → Action Requests. Requests expire 15 minutes after
   creation and cannot execute without a matching unexpired confirmation.

Switch to Administrator from the account menu to reach the Administration section.

## Structure

```text
src/
  app/          Shell, routing, session context, sidebar, top bar
  components/   Icon, Menu, Modal, Toast, CommandPalette
  features/
    chat/       Composer, message timeline, input parsing
    canvas/     Filterable work-item table
    actions/    Action request dialog and lifecycle
    activity/   Session timeline
    settings/   Tools, credentials, health
  hooks/        Persistent state, hotkeys, media queries, run polling
  api/          Typed HTTP client and error normalisation
  types/        Contracts mirroring backend/schemas.py
  styles/       Design tokens and base primitives
```

## Styling

All colour, spacing, type, radius, elevation, and motion values live in `src/styles/tokens.css`.
Light and dark themes are token overrides on `[data-theme]`; no component stylesheet contains a
literal colour.

`src/main.tsx` imports `tokens.css` and `base.css` **before** any feature module. Vite emits CSS in
import-evaluation order and base primitives share single-class specificity with component rules, so
importing them last silently overrides component styling.

## Known backend gaps surfaced in the UI

- Runs stay `queued` — there is no orchestration worker yet. Polling stops after 30 seconds and the
  run card says so.
- Canvas rows are derived from submitted input; the backend does not persist `CanvasWorkItem` records.
- Credential management and connector diagnostics have no endpoints, so those views are inert and
  document what they need rather than faking a working screen.
- There are no list endpoints for runs or actions, so history is per-browser `localStorage`.

## Troubleshooting

**"Cannot reach the Fleet Recon API"** — the backend is not running, or `VITE_API_PROXY_TARGET`
points somewhere else. Check `curl http://127.0.0.1:8000/api/v1/health`.

**403 on an Administration screen** — the simulated role is `workspace_user`. Switch from the
account menu; the view refetches automatically.

**Stale thread or canvas rows** — history is stored in `localStorage`. Use *Clear* in the chat
toolbar, or clear site data.
