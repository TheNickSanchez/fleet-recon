# Fleet Recon Frontend Implementation — General Chat Pivot

**Product pivot, 2026-08-31 — this document supersedes the session-host-rebuild record below it (2026-08-30), which itself superseded the original enterprise-scaffold record.** The backend dropped its two-mode router (`device_lookup`/`asset_ops`, chosen by a client-side identity-count preview) for a single general chat turn per message — see `backend.md`'s 2026-08-31 entry for the full backend-side reasoning. This pass follows that contract change: the composer no longer gates on "did we detect an identity," result rendering is a single markdown chat bubble instead of two specialized card types, and there is a `thread_id` for real multi-turn conversation instead of a purely client-local "thread."

React 19 + TypeScript + Vite, same stack as the superseded pass.

## What Changed vs. the 2026-08-30 Rebuild

| Area | Disposition |
| --- | --- |
| `types/api.ts`, `api/client.ts` | **Rewritten.** `RunMode`/`skill_id`/`intent_id`/`input_count` are gone — a `RunSummary` now carries `thread_id` instead. `RunResult` is just `{type: "chat.text", text}`; `CsvPreviewResult`/`DeviceCardResult` and their type guards are gone. `api.createRun({text, file, threadId})` replaces the separate `createRunFromText`/`createRunFromFile` — a single call now supports text, a file, or both together (the backend's `_build_prompt` combines them into one prompt). |
| `features/chat/parseInput.ts` | **Gutted.** No more identity extraction / mode-bind preview (that logic moved server-side into the now-deleted `preprocessor.py`, and doesn't exist anywhere anymore — every message is submittable). Kept only the CSV upload guardrails (`validateCsv`, 5 MiB cap, `.csv` extension). |
| `features/chat/Composer.tsx` | **Rewritten.** Submit is gated on "there's text or a file," not "we detected ≥1 identity." A CSV attach is now **staged** (a removable chip above the input) instead of firing an immediate separate submission — you can attach a file, add a note, and send both together in one turn, matching the backend's combined-prompt support. |
| `features/chat/Message.tsx`, `ResultCards.tsx` | **Merged and simplified.** `ResultCards.tsx` (the `chat.csv_preview` table card and `chat.device_card` conversational card) is deleted; every completed run now renders as one markdown block (`react-markdown`, reused from the prior pass's device-card fix) directly inside `Message.tsx`. Status badges dropped the per-mode label (`MODE_LABEL`) and the `partial` status/tone — there is no more "partial" run status. |
| `features/canvas/*` | **Deleted outright** (`CanvasPage.tsx`, `CanvasPanel.tsx`, `CanvasView.tsx`/`.css`), along with `components/ReportDownloadButton.tsx` and `lib/csv.ts`. All three existed specifically to visualize/export the structured `chat.csv_preview` payload, which no longer exists as a distinct result type — the asset-report tool's output is now narrated by the model as part of its normal chat.text response (often still as a markdown table, just not a separate structured card/canvas). This is a real feature removal, not a rename; see Open Questions if a dedicated data-table view is wanted back. |
| `app/AppState.tsx` | **Simplified.** Dropped the `canvas`/`registerRunResult`/`clearCanvas`/`canvasOpen` slot entirely (no more data source for it). Added `threadId` (a `sessionStorage`-backed uuid, regenerated on "New chat") so every message in a browser session threads into the same backend conversation (`RunStore.get_thread_history`) until explicitly cleared. |
| `app/App.tsx`, `app/TopBar.tsx`, `main.tsx` | **Simplified.** No more `/canvas` route or narrow-viewport tab switcher — there is exactly one screen now. `react-router-dom` was removed as a dependency entirely (nothing in the app routes anymore). |
| `features/chat/Message.tsx`, `Message.css` | **[New, same day] Live activity feed + table rendering fix.** Two live-demo bugs from the first pivot pass: (1) markdown tables rendered as raw `\|`-delimited text — `react-markdown@10` needs `remark-gfm` for GFM tables/strikethrough/task-lists and it wasn't wired up; fixed by adding the `remark-gfm` dependency and passing `remarkPlugins={[remarkGfm]}`. (2) the static "Thinking, and calling whichever tools it needs..." summary + indeterminate progress bar read as broken during a real ~30s multi-tool turn ("it's static while looking up... with claude, at least you can see it thinking" — operator). Replaced with a live feed rendering the new `RunSummary.activity` lines (last 5, newest highlighted) — see `backend.md`'s "Live Activity Feed" for what populates it. |

## Interaction Design Decisions

| Decision | Rationale |
| --- | --- |
| **Anything is submittable.** | The old "one surviving identity → lookup, two+ → batch, zero → nothing to submit" preview is gone — the backend has no concept of a rejected zero-identity submission anymore (`VALIDATION_ERROR` now only fires on a genuinely empty submit: no text *and* no file). |
| **Attachments are staged, not fire-and-forget.** | The prior pass uploaded a CSV the instant it was picked/dropped, as its own timeline entry. This pass stages it as a removable chip and sends it together with whatever text is in the composer on the next `Enter`/send click — matching the backend's ability to combine `text` + `file` into one prompt for the model. |
| **One result shape: a markdown chat message.** | There is no more per-mode result card. `chat.text` is always rendered through `react-markdown` inside `.markdown`-scoped typography (same compact heading/list/table/code styling introduced in the prior pass's device-card fix, now the *only* rendering path instead of one of three). |
| **Conversations actually continue.** | `threadId` is sent with every `POST /api/v1/runs` after the first message in a session, so a follow-up like "what did I just ask you?" works — verified live against the real backend (see `backend.md`'s Live Smoke Test). "New chat" clears the local timeline *and* rolls a new `threadId`, so it also starts a fresh thread server-side rather than just hiding old messages while secretly still appending to the same backend history. |
| **No canvas, no data-table view — for now.** | This was a deliberate scope decision following the operator's explicit "general chat, like claude.ai" answer over "keep specialized structured cards." The asset-report tool's rows still exist (the model narrates them, often as a markdown table in the response), but there is no dedicated sortable/filterable/exportable table view anymore. Flagged as an Open Question below in case that's wanted back for large reports. |
| **Session-only history, unchanged.** | Still `sessionStorage`-backed (thread entries + `threadId`), still disclosed in the empty state. `usePersistentState` (`localStorage`) is still theme-only. |
| **No nav rail, no canvas toggle, no routing.** | The top bar is now just brand + theme toggle — there is one screen, so there is nothing to switch between. `react-router-dom` was removed from `package.json` since nothing imports it anymore. |
| **A live activity feed, not a static spinner, while a run is `running`.** | Message-level tool-call/result progress (from `RunSummary.activity`) is enough to make a real ~30-45s multi-tool turn feel alive instead of hung — matches the "with claude, at least you can see it thinking" operator feedback without needing token-level streaming (which the SDK's `sdk.query()` doesn't expose without `include_partial_messages`, not adopted this pass — see Open Questions). |

## Routes & Screens

Just `/` — a single chat screen. There is no `/canvas` route anymore (deleted, see above), no
`/workspaces/:id/*`, no settings/actions/activity/health routes (unchanged from the prior pass — no
backing endpoints exist for any of those).

## API Integration

`src/api/client.ts` wraps the entire live API (still 4 routes total, per `backend.md`):

| Method | Endpoint | Client function |
| --- | --- | --- |
| `GET` | `/api/v1/health`, `/api/v1/ready` | *(not called by this client, unchanged)* |
| `POST` | `/api/v1/runs` (JSON `{text, thread_id}` or multipart `file`+`text`+`thread_id`) | `api.createRun({text, file, threadId})` — single function, replaces the prior pass's `createRunFromText`/`createRunFromFile` split |
| `GET` | `/api/v1/runs/{run_id}` | `api.getRun` (polled by `useRunPolling`, unchanged) — response now also carries `activity: string[]` (**[new, same day]**), rendered as a live feed by `Message.tsx` while `status === "running"` |

Error handling (`ApiError`, the `{error:{code,message}}` envelope, network-failure messaging) is
unchanged — the error contract itself didn't change in this pivot, only the success-path result
shape and the request body's new `thread_id` field.

## Accessibility

Unchanged in substance from the prior pass (full keyboard operation, visible focus rings, semantic
markup, live regions for status transitions, no color-only status, `prefers-reduced-motion`) — none
of it depended on the deleted canvas/mode-card surfaces. The one removed accessibility-relevant
control is `ReportDownloadButton`'s always-visible disabled-state explanation, since the control
itself (and the full-report route it was waiting on) no longer has a UI surface to attach to.

## Validation

- `npx tsc -b` (and `--force`) — clean, no errors.
- `npx oxlint src` — same pre-existing warning categories as the prior pass (`set-state-in-effect` on
  legitimate async-load effects — including the new Composer file-attach flow; `only-export-components`
  fast-refresh advisories), no new categories introduced.
- `npm run build` — succeeds; `dist/assets/index-*.js` **399 kB (122.5 kB gzip)**, up from 360 kB
  (111.6 kB gzip) after adding `remark-gfm` for the table-rendering fix (see "What Changed") — still
  well below the original 410 kB (128 kB gzip) enterprise-scaffold pass.
- **Live backend contract validated directly** (not just typechecked against prose): the real
  `session-host` process was exercised with `curl` for a general open-ended question, a real
  `nick.sanchez` lookup, and a two-turn memory test — see `backend.md`'s Live Smoke Test for the
  actual request/response pairs this client's types were built against.
- **[Resolved, same day] Live browser round-trip through the actual Vite dev-server proxy.** The
  original pivot pass hit an environment-specific issue where a `nohup ... & disown`-detached dev
  server was unreachable across separate shell tool calls in this sandbox. Root-caused: launching
  `npm run dev` as a normal foreground command (which the tool harness itself moves to background
  after a timeout, keeping it attached to a tracked shell) stays reachable across calls; the earlier
  failure was from manually detaching it (`nohup`+`disown`) into a shell the harness no longer
  tracks, not a code defect. Re-verified live through `http://localhost:5173` (the actual dev-server
  proxy origin, not a direct backend call): a general chat turn, two-turn memory, and the
  `nick.sanchez` lookup (34.1s, full markdown response including tables) all round-tripped
  correctly.

## Development Workflow

**[New, same day]** One-command launcher for a local demo, `scripts/dev.sh` (repo root): frees
stale 8100/5173 listeners, starts the session host, polls `/health` until it's actually up (not
just "process started"), warns on a `/ready` problem, auto-creates `frontend/.env.local` if
missing, then runs the frontend dev server in the foreground so `Ctrl+C` stops both.

```bash
./scripts/dev.sh
```

Or by hand, in two terminals:

```bash
# Terminal 1
cd session-host && uv run python -m fleet_session_host
# Listens on 127.0.0.1:8100

# Terminal 2
cd frontend && npm install && cp .env.example .env.local && npm run dev
# http://localhost:5173
```

## Directory Structure

```text
frontend/src/
  app/          App.tsx, AppState.tsx, TopBar.tsx, AppShell.css
  components/   Icon, Menu, Toast (+ styles)
  features/
    chat/       ChatView, Composer, Message (renders chat.text via react-markdown), parseInput (CSV guardrails only)
  hooks/        usePersistentState (+ useSessionState, useHotkey, useMediaQuery), useRunPolling
  api/          client.ts
  types/        api.ts
  styles/       tokens.css, base.css
```

`features/canvas/`, `ResultCards.tsx`/`.css`, `ReportDownloadButton.tsx`, and `lib/csv.ts` from the
prior pass no longer exist.

## Assumptions

1. "Attach a CSV" staging (send-together-with-text) rather than immediate-fire-on-select is a UX
   improvement consistent with the backend's new combined-prompt support, not something explicitly
   requested — flagged here in case the operator prefers the old immediate-fire behavior.
2. Dropping the canvas/data-table view entirely (rather than, say, keeping it as an optional view of
   any markdown table the model happens to return) follows directly from the operator's explicit
   "general chat, like claude.ai" choice over "keep specialized structured cards" — revisit if a
   large asset report turns out to be hard to read as a chat-embedded markdown table.
3. `threadId` reset on "New chat" is read as the obviously-intended behavior of that button (start
   over, including server-side memory) — not separately confirmed with the operator.

## Open Questions / Known Gaps

| Gap | Cause | Handling |
| --- | --- | --- |
| No data-table/canvas view for large asset reports | Deliberately dropped this pass (see Assumptions #2) | The model narrates rows as markdown text/tables in the chat message; a very large report (dozens+ rows) may be unwieldy to read this way — revisit if that turns out to matter in practice |
| Frontend is still `localhost`-only; the operator's stated audience is local-network colleagues | `backend.md`'s Known Gaps — the backend itself is still bound to `127.0.0.1` with no CORS | Explicitly scoped out for now — operator confirmed the near-term need is a single-machine/screen-shared demo, not colleagues opening it on their own laptops. `@devops.eng`/`deploy.md` pass (host bind, CORS or reverse proxy) still needed before that changes. |
| No authentication of any kind | Unchanged from the prior pass, and now materially higher-stakes (13 real MCP servers attached, not 3 narrow ones) | Nothing in this client simulates or requires identity; matches the operator's explicit "no access control for now" answer |
| No SSE/WebSocket | Unchanged — still two-phase bounded polling (2.5s fast / 8s slow / 2-minute hard stop) | A general chat turn calling several tools can still take under a minute; the new `activity` feed (see "What Changed") gives per-tool-call progress within that window instead of a static spinner, but it is still polling, not push |
| Activity feed is message-level, not token-level | `sdk.query()` yields whole content blocks, not streaming deltas, unless `include_partial_messages=True` (not adopted — bigger change, more chatty wire protocol) | Good enough to show "what tool is running now," not a token-by-token typing effect like claude.ai's final answer text |

## Sources

- Operator direction, 2026-08-31 (see `backend.md`'s Sources for the exact quotes) and the resulting
  backend pivot.
- `project-context/2.build/backend.md` (2026-08-31 entry) — the new API contract this pass mirrors.
- Live `curl` exercises against the real running `session-host` (see `backend.md`'s Live Smoke Test)
  — this pass's types were written against those actual responses, not just backend.md's prose.
- Prior `frontend.md` (2026-08-30 rebuild) — preserved in git history; its design-system, theming,
  and accessibility sections are the basis for everything marked "unchanged" above.

## Audit

- **Timestamp:** 2026-08-31
- **Persona id:** `frontend-eng` (pivot; superseding the 2026-08-30 rebuild record)
- **Actions:** operator-directed product pivot, `develop-fe`, `document-frontend`
- **What was done:** rewrote `types/api.ts`/`api/client.ts` for the new `thread_id`/`chat.text`
  contract; gutted `parseInput.ts` to CSV-only guardrails; rewrote `Composer.tsx` (staged attach,
  no identity gate); merged `ResultCards.tsx` into `Message.tsx` (single markdown result path);
  deleted `features/canvas/*`, `ReportDownloadButton.tsx`, `lib/csv.ts`; simplified `AppState.tsx`
  (dropped canvas state, added `threadId`), `App.tsx`, `TopBar.tsx`, `main.tsx` (dropped
  `react-router-dom` entirely, now removed from `package.json`); ran `npx tsc -b` (clean),
  `npx oxlint src` (same pre-existing warnings, no new categories), `npm run build` (360 kB JS /
  111.6 kB gzip, down from 410 kB / 128 kB).
- **Runtime library versions:** `react@19.2.8`, `react-dom@19.2.8`, `@tanstack/react-query@5.102.8`,
  `react-markdown@10.1.0`, `typescript@6.0.2`, `vite@8.2.2`, `oxlint@1.79.0` — `react-router-dom`
  removed (`npm uninstall`, 4 packages removed).
- **Prompt Trace:** omitted — deterministic rewrite against a directly-preceding backend contract
  change and live-validated API responses, not a model-authored product decision requiring trace
  capture per `aamad-core.mdc`.
- **Security:** no secrets read or written; no real employee/device data was copied into any tracked
  file (the live responses referenced in `backend.md` were read, not persisted, by this pass).

### Follow-up Audit — same day, demo readiness + live activity feed

- **Timestamp:** 2026-08-31 (later same day)
- **Persona id:** `frontend-eng`
- **Actions:** operator ask ("i want it to work locally so we can run it for a demo"), then two bug
  reports ("it's static while looking up... with claude, at least you can see it thinking" /
  "tables do not render in markdown"), `develop-fe`, `document-frontend`
- **What was done:**
  - Added `scripts/dev.sh` (one-command local launcher) and rewrote `frontend/README.md`'s Quick
    Start/Using it/Structure/Known-gaps sections, which had not been updated for the pivot and still
    described the deleted mode-router/canvas UI.
  - Live-verified the full stack through the actual Vite proxy origin (`localhost:5173`, not a
    direct backend call) — general chat, multi-turn memory, and a real `nick.sanchez` lookup
    (34.1s) — root-causing and resolving the earlier "not done this pass" browser-round-trip gap
    (see "Validation").
  - Added `remark-gfm` and wired `remarkPlugins={[remarkGfm]}` into `Message.tsx`'s `ReactMarkdown`
    call, fixing GFM tables rendering as raw `\|`-delimited text.
  - Added `RunSummary.activity: string[]` to `types/api.ts`; replaced `Message.tsx`'s static
    "Thinking..." summary + indeterminate progress bar with a live feed of the last 5 `activity`
    lines (newest highlighted, `checkCircle` on settled lines, spinning icon on the current one);
    replaced the corresponding CSS (`.msg__activity*` in `Message.css`, removed the old
    `.msg__progress*`/`@keyframes indeterminate`).
  - `npm run build` — clean (see "Validation" for updated bundle size).
- **Runtime library versions:** added `remark-gfm@4` (checked in `package.json`/`package-lock.json`);
  no other dependency changes.
- **Prompt Trace:** omitted — deterministic bug fixes (missing plugin wiring, missing progress
  surface) driven directly by operator-reported, reproduced defects, not a model-authored product
  decision requiring trace capture per `aamad-core.mdc`.
- **Security:** no secrets read or written; live-test responses (the `nick.sanchez` profile/asset
  data) were read for verification only, not persisted into this document or any other tracked file
  beyond field-name-level description, matching the standing pattern from the initial pivot pass.

---

*The 2026-08-30 session-host-rebuild record (workspace/admin/action-request removal, the original
mode-router-based `types/api.ts`/`Composer`/canvas build) that this document superseded has been
removed from this file to keep it navigable; recover it from git history
(`git log -p -- project-context/2.build/frontend.md`) if needed.*
