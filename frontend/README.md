# Fleet Recon — Frontend

React 19 + TypeScript + Vite general chat client for the Fleet Recon session host.

Product pivot 2026-08-31: this is a general chat interface — "Claude, but with your Claude Code
skills and MCP tools already attached." There is no mode router (device lookup vs. batch report)
anymore; every message is one turn of one conversation. See
[`project-context/2.build/backend.md`](../project-context/2.build/backend.md) and
[`project-context/2.build/frontend.md`](../project-context/2.build/frontend.md) for the full
contract and design rationale.

## Quick start

The easiest way to run both services for a local demo is the one-command launcher from the
repository root:

```bash
./scripts/dev.sh
```

It starts the session host, waits for it to report healthy, and then starts the frontend dev
server — `Ctrl+C` stops both. It expects a repo-root `.env` (copy `.env.example` first) with
`ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` / `LITELLM_MODEL` filled in.

To run the two services by hand instead:

```bash
# Terminal 1, from the repository root
cd session-host && uv run python -m fleet_session_host
# Listens on 127.0.0.1:8100

# Terminal 2
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open <http://localhost:5173>.

> The dev server proxies `/api` to the session host. It sends no CORS headers, so the browser
> must stay same-origin — keep `VITE_API_BASE_URL` as the relative `/api/v1` unless you put the
> host behind a CORS-enabled reverse proxy. This means the app is only reachable from the machine
> running the dev server — see `backend.md`'s Known Gaps if you need it reachable from other
> machines on the network.

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
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8100` | Where the dev server forwards `/api` |
| `VITE_PORT` | `5173` | Dev/preview port |

There is no dev-role/actor/workspace configuration and no authentication. The session host is a
private bind with no per-actor identity at all — access control is "run this only where it should
be reachable," not a client-presentable claim.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Enter` | Send the composer message |
| `Shift`+`Enter` | New line in the composer |
| `Esc` | Dismiss the attach menu |

## Using it

1. **Ask anything.** There's no identity-count routing anymore — a general question, a device
   lookup, a request to search a ticket system, whatever your attached MCP tools support all go
   through the same composer and the same conversation.
2. **Attach a CSV** (`+` menu or drag-and-drop, under 5 MiB) alongside a note, or on its own. The
   model decides whether to call the asset-report tool on it.
3. **Conversations remember context.** Follow-up messages in the same session thread into the same
   backend conversation — you don't need to re-state what you already told it.
4. **Responses are markdown**, rendered with headings, lists, tables, and inline code — not raw
   text.
5. **"New chat"** in the toolbar clears the local timeline and starts a fresh backend conversation
   (no shared memory with the old thread).

## Structure

```text
src/
  app/          Shell, app-wide state (theme/thread), top bar
  components/   Icon, Menu, Toast
  features/
    chat/       Composer, message timeline (markdown rendering), CSV upload guardrails
  hooks/        Persistent/session state, hotkeys, media queries, run polling
  api/          Typed HTTP client and error normalisation
  types/        Contracts mirroring the session host's run/result shapes
  styles/       Design tokens and base primitives
```

**Explicitly not present**: workspace routing, an administrator role/claim model, a canvas/
data-table view, Tools/Credentials settings screens, Action Requests (create/confirm/execute), and
a `/health` diagnostics screen. None of those have a backing route on this backend.

## Styling

All colour, spacing, type, radius, elevation, and motion values live in `src/styles/tokens.css`.
Light and dark themes are token overrides on `[data-theme]`; no component stylesheet contains a
literal colour. Visual direction: modern-minimal-saas (generous whitespace, restrained color, one
accent), per `aamad.config.yml`'s `ui:` block.

`src/main.tsx` imports `tokens.css` and `base.css` **before** any feature module. Vite emits CSS in
import-evaluation order and base primitives share single-class specificity with component rules, so
importing them last silently overrides component styling.

## Known backend gaps surfaced in the UI

- No SSE/WebSocket — the client polls `GET /runs/{id}`: fast (every 2.5s) for the first 30 seconds,
  then slow (every 8s) up to a 2-minute hard stop, so a run that calls several tools in sequence
  still resolves on its own. Past 2 minutes it stops and explains why rather than spinning forever.
- A first-time lookup of anything (a device, a person) takes ~30-45s — it's a real multi-turn agent
  session hitting real vendor APIs, not a cached/instant response. There is currently no cache
  (the prior narrow `device_lookup` skill had one; it didn't carry over to general chat — see
  `backend.md`'s Known Gaps). Set demo expectations accordingly, or pre-warm a lookup you plan to
  show by running it once before the audience is watching.
- No server-side conversation list or audit log — chat history is derived client-side and kept only
  in `sessionStorage` (cleared when the tab closes), disclosed as such in the empty state.
- No authentication — the private bind is the only access control, and the chat session now has 13
  real MCP tools attached (ServiceNow, Jamf, Intune, Tenable, Atlassian, Slack, Google Workspace).
- Still `localhost`-only — not reachable from other machines on the network without further work
  (host bind + CORS). Fine for a single-machine, screen-shared demo; not yet fine for colleagues to
  open on their own laptops.

## Troubleshooting

**"Cannot reach the Fleet Recon session host"** — it isn't running, or `VITE_API_PROXY_TARGET`
points somewhere else. Check `curl http://127.0.0.1:8100/api/v1/health`.

**`GET /api/v1/ready` reports a problem** — usually `CLAUDE_CONFIG_PATH` (default `~/.claude.json`)
not found, or `ASSET_OPS_SCRIPTS_DIR` missing. Fix the reported path and restart.

**A run never leaves "Queued"** — confirm `ANTHROPIC_BASE_URL`/`ANTHROPIC_API_KEY`/`LITELLM_MODEL`
are filled in in the repo-root `.env`; the host returns a `failed` Diagnostic rather than hanging
once those are set correctly.

**Stale thread** — history is `sessionStorage`-backed on purpose (browser-session-only, no server
audit log). Use *New chat* in the chat toolbar, or close the tab.
