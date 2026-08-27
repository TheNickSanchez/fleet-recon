from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Role(StrEnum):
    WORKSPACE_USER = "workspace_user"
    ADMINISTRATOR = "administrator"


class InputKind(StrEnum):
    TYPED = "typed"
    PASTED = "pasted"
    CSV = "csv"


class RunMode(StrEnum):
    MICRO_QUERY = "micro_query"
    BATCH_AUTOMATION = "batch_automation"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class RunRequest(BaseModel):
    input_kind: InputKind
    text: str = Field(min_length=1, max_length=100_000)
    intent: str | None = Field(default=None, max_length=1_000)


class RunSummary(BaseModel):
    id: UUID
    workspace_id: UUID
    input_kind: InputKind
    input_count: int
    rejected_count: int
    mode: RunMode
    status: RunStatus
    correlation_id: UUID
    created_at: datetime


class ApiErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, str]] = []


class ApiError(BaseModel):
    error: ApiErrorBody
    correlation_id: UUID


class ToolConfigPatch(BaseModel):
    enabled: bool
    assigned_agents: set[str] = Field(default_factory=set)
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_version: int = Field(ge=1)


class ToolConfigView(BaseModel):
    tool_id: str
    display_name: str
    integration: str
    version: str
    enabled: bool
    assigned_agents: set[str]
    parameters: dict[str, Any]
    configuration_version: int


class ActionRequestCreate(BaseModel):
    work_item_ids: list[UUID] = Field(min_length=1, max_length=100)
    connector: str
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ActionRequestView(BaseModel):
    id: UUID
    workspace_id: UUID
    work_item_ids: list[UUID]
    connector: str
    operation: str
    status: str
    expires_at: datetime
    idempotency_key: UUID


class Finding(BaseModel):
    category: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    recommendation: str
    approval_required: bool


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
