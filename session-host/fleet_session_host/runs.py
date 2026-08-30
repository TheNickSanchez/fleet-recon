"""In-memory query-run record (SAD §2.1, PRD §5, FR-1).

Session files / process memory are the retention for this MVP -- no
PostgreSQL (SAD §1.3, §4.4 Future Work). ``mode``, ``skill_id``, and
``intent_id`` are set once at bind time and never mutated afterward (FR-2:
"a request never changes route mid-run").
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

RunStatus = Literal["queued", "running", "partial", "completed", "failed", "rejected"]

SKILL_ID = "lookup-user-devices"


@dataclass
class Run:
    id: str
    correlation_id: str
    skill_id: str
    intent_id: str
    mode: str | None
    input_kind: Literal["text", "csv"]
    input_count: int
    status: RunStatus
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    diagnostic: str | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "correlation_id": self.correlation_id,
            "skill_id": self.skill_id,
            "intent_id": self.intent_id,
            "mode": self.mode,
            "input_kind": self.input_kind,
            "input_count": self.input_count,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error": self.error,
            "diagnostic": self.diagnostic,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    """Thread-safe in-memory run table. One process, one session host."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, Run] = {}

    def create(
        self,
        *,
        mode: str | None,
        input_kind: Literal["text", "csv"],
        input_count: int,
        intent_id: str,
        status: RunStatus = "queued",
    ) -> Run:
        run_id = str(uuid.uuid4())
        run = Run(
            id=run_id,
            correlation_id=run_id,
            skill_id=SKILL_ID,
            intent_id=intent_id,
            mode=mode,
            input_kind=input_kind,
            input_count=input_count,
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


_store = RunStore()


def get_store() -> RunStore:
    return _store
