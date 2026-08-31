#!/usr/bin/env bash
# One-command local demo launcher: starts the session host in the background,
# waits for it to be healthy, then runs the frontend dev server in the
# foreground so Ctrl+C stops both cleanly.
#
# Usage: ./scripts/dev.sh   (from the repository root)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${SESSION_HOST_PORT:-8100}"
FRONTEND_PORT="${VITE_PORT:-5173}"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo ""
    echo "Stopping session host (pid $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

free_port() {
  local port="$1"
  local pid
  pid="$(lsof -ti "tcp:$port" 2>/dev/null || true)"
  if [[ -n "$pid" ]]; then
    echo "Port $port is in use (pid $pid) -- stopping it first."
    kill -9 $pid 2>/dev/null || true
    sleep 1
  fi
}

echo "== Fleet Recon local demo launcher =="

if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "No .env found at repo root -- copy .env.example and fill in ANTHROPIC_BASE_URL /" \
       "ANTHROPIC_API_KEY / LITELLM_MODEL before running a demo." >&2
  exit 1
fi

free_port "$BACKEND_PORT"
free_port "$FRONTEND_PORT"

echo "-- Starting session host on 127.0.0.1:$BACKEND_PORT --"
(cd "$REPO_ROOT/session-host" && uv run python -m fleet_session_host) &
BACKEND_PID=$!

echo -n "Waiting for the session host to be healthy"
for _ in $(seq 1 30); do
  if curl -s -o /dev/null "http://127.0.0.1:$BACKEND_PORT/api/v1/health"; then
    echo " -- up."
    break
  fi
  echo -n "."
  sleep 1
done

if ! curl -s -o /dev/null "http://127.0.0.1:$BACKEND_PORT/api/v1/health"; then
  echo ""
  echo "Session host did not come up in time -- check the output above for a Diagnostic." >&2
  exit 1
fi

READY="$(curl -s "http://127.0.0.1:$BACKEND_PORT/api/v1/ready")"
echo "Readiness check: $READY"
case "$READY" in
  *'"status":"ok"'*) ;;
  *) echo "Warning: session host reports problems above -- MCP tools or asset-ops may not work." >&2 ;;
esac

if [[ ! -f "$REPO_ROOT/frontend/.env.local" ]]; then
  cp "$REPO_ROOT/frontend/.env.example" "$REPO_ROOT/frontend/.env.local"
  echo "Created frontend/.env.local from .env.example (defaults are fine for a local demo)."
fi

echo "-- Starting frontend on http://localhost:$FRONTEND_PORT --"
echo "   (Ctrl+C stops both the frontend and the session host)"
cd "$REPO_ROOT/frontend"
npm run dev
