"""In-memory chat-run record (product pivot 2026-08-31 -- see backend.md
Audit).

Session files / process memory are the retention for this MVP -- no
PostgreSQL. Each ``Run`` is one turn of a ``thread_id``-scoped conversation;
``RunStore`` also tracks the last Claude Agent SDK ``session_id`` per thread
so the next turn in that thread can ``resume`` it (see ``chat.py``) instead
of losing context between HTTP requests.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

RunStatus = Literal["queued", "running", "completed", "failed"]


@dataclass
class Run:
    id: str
    correlation_id: str
    thread_id: str
    input_kind: Literal["text", "csv"]
    status: RunStatus
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    diagnostic: str | None = None
    # Live "what is it doing right now" feed -- e.g. "Calling Jamf...", "Got a
    # result back". Appended to while status=="running" so the client can show
    # something other than a static spinner (see backend.md Audit 2026-08-31).
    activity: list[str] = field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "thread_id": self.thread_id,
            "input_kind": self.input_kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error": self.error,
            "diagnostic": self.diagnostic,
            "activity": self.activity,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


Turn = tuple[Literal["user", "assistant"], str]

# Cap on how much prior conversation gets stuffed into the next turn's prompt
# (see chat.py's `_render_history`). The SDK's own `resume` was tried first
# and rejected live 2026-08-31: it depends on Anthropic's server-side session
# persistence, which a third-party LiteLLM gateway does not implement ("No
# conversation found with session ID: ..." on every second turn even though
# the id round-tripped correctly). Context-stuffing works with any gateway
# at the cost of unbounded growth, hence the cap -- no compaction/summarization
# yet (see backend.md Open Questions).
MAX_HISTORY_TURNS = 12


class RunStore:
    """Thread-safe in-memory run table. One process, one session host."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, Run] = {}
        self._thread_history: dict[str, list[Turn]] = {}

    def create(
        self,
        *,
        thread_id: str,
        input_kind: Literal["text", "csv"],
        status: RunStatus = "queued",
    ) -> Run:
        run_id = str(uuid.uuid4())
        run = Run(
            id=run_id,
            correlation_id=run_id,
            thread_id=thread_id,
            input_kind=input_kind,
            status=status,
            created_at=_now(),
            updated_at=_now(),
        )
        with self._lock:
            self._runs[run_id] = run
        return run

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def update(self, run_id: str, **fields: Any) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            for key, value in fields.items():
                setattr(run, key, value)
            run.updated_at = _now()

    def append_activity(self, run_id: str, line: str) -> None:
        """Append one line to a running turn's live activity feed. A no-op if
        the run has already reached a terminal status (or vanished) -- the
        chat turn's background asyncio task can outlive interest in its
        progress, but never a completed/failed run's final state."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None or run.status not in ("queued", "running"):
                return
            run.activity.append(line)
            run.updated_at = _now()

    def get_thread_history(self, thread_id: str) -> list[Turn]:
        with self._lock:
            return list(self._thread_history.get(thread_id, []))

    def append_thread_history(self, thread_id: str, role: Literal["user", "assistant"], text: str) -> None:
        with self._lock:
            history = self._thread_history.setdefault(thread_id, [])
            history.append((role, text))
            if len(history) > MAX_HISTORY_TURNS:
                del history[: len(history) - MAX_HISTORY_TURNS]


_store = RunStore()


def get_store() -> RunStore:
    return _store
