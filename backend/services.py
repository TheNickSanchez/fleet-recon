from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from .schemas import (
    ActionRequestCreate,
    ActionRequestView,
    Finding,
    InputKind,
    Role,
    RunMode,
    RunRequest,
    RunStatus,
    RunSummary,
    ToolConfigPatch,
    ToolConfigView,
    now_utc,
)
from .security import Actor

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%+@-]{0,254}$")
ALLOWED_ACTIONS = {("servicenow", "create_ticket"), ("jamf", "trigger_policy")}


@dataclass
class StoredRun:
    summary: RunSummary
    usernames: list[str]


class FleetReconService:
    """Deterministic application service; replace dictionaries with repositories in integration work."""

    def __init__(self) -> None:
        self.runs: dict[UUID, StoredRun] = {}
        self.actions: dict[UUID, ActionRequestView] = {}
        self.tools: dict[str, ToolConfigView] = {
            "asset_report_build": ToolConfigView(
                tool_id="asset_report_build", display_name="Asset report build",
                integration="servicenow", version="1.0.0", enabled=True,
                assigned_agents={"orchestrator"}, parameters={"states": ["In use"]},
                configuration_version=1,
            ),
            "asset_report_mdm": ToolConfigView(
                tool_id="asset_report_mdm", display_name="Asset report MDM",
                integration="jamf_intune", version="1.0.0", enabled=True,
                assigned_agents={"orchestrator"}, parameters={"jamf_batch_size": 40},
                configuration_version=1,
            ),
            "asset_report_app": ToolConfigView(
                tool_id="asset_report_app", display_name="Asset report application",
                integration="jamf_intune", version="1.0.0", enabled=True,
                assigned_agents={"orchestrator", "analysis"}, parameters={},
                configuration_version=1,
            ),
        }

    @staticmethod
    def sanitize_usernames(text: str) -> tuple[list[str], int]:
        clean_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).replace("\r\n", "\n")
        candidates = re.split(r"[\s,;]+", clean_text)
        accepted: list[str] = []
        seen: set[str] = set()
        rejected = 0
        for candidate in candidates:
            username = candidate.strip()
            if not username:
                continue
            key = username.casefold()
            if not USERNAME_PATTERN.fullmatch(username):
                rejected += 1
            elif key not in seen:
                seen.add(key)
                accepted.append(username)
        return accepted, rejected

    @staticmethod
    def route(input_kind: InputKind, usernames: list[str]) -> RunMode:
        if input_kind == InputKind.CSV or len(usernames) > 5:
            return RunMode.BATCH_AUTOMATION
        return RunMode.MICRO_QUERY

    def create_run(self, workspace_id: UUID, request: RunRequest, actor: Actor) -> RunSummary:
        usernames, rejected = self.sanitize_usernames(request.text)
        if not usernames:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="No valid usernames were found.",
            )
        summary = RunSummary(
            id=uuid4(), workspace_id=workspace_id, input_kind=request.input_kind,
            input_count=len(usernames), rejected_count=rejected,
            mode=self.route(request.input_kind, usernames), status=RunStatus.QUEUED,
            correlation_id=uuid4(), created_at=now_utc(),
        )
        self.runs[summary.id] = StoredRun(summary=summary, usernames=usernames)
        return summary

    def create_csv_run(self, workspace_id: UUID, content: bytes, actor: Actor) -> RunSummary:
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV exceeds the configured 5 MiB limit.")
        try:
            decoded = content.decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(decoded)))
        except (UnicodeDecodeError, csv.Error) as error:
            raise HTTPException(status_code=422, detail="CSV must be valid UTF-8 with headers.") from error
        if len(rows) > 10_000 or not rows or "username" not in (rows[0] or {}):
            raise HTTPException(status_code=422, detail="CSV requires a username column and at most 10,000 rows.")
        return self.create_run(workspace_id, RunRequest(input_kind=InputKind.CSV, text="\n".join(row.get("username", "") for row in rows)), actor)

    def get_run(self, workspace_id: UUID, run_id: UUID) -> RunSummary:
        run = self.runs.get(run_id)
        if run is None or run.summary.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Query run not found.")
        return run.summary

    def update_tool(self, tool_id: str, patch: ToolConfigPatch) -> ToolConfigView:
        tool = self.tools.get(tool_id)
        if tool is None:
            raise HTTPException(status_code=404, detail="Tool definition not found.")
        if patch.expected_version != tool.configuration_version:
            raise HTTPException(status_code=409, detail="Tool configuration version conflict.")
        updated = tool.model_copy(update={
            "enabled": patch.enabled, "assigned_agents": patch.assigned_agents,
            "parameters": patch.parameters, "configuration_version": tool.configuration_version + 1,
        })
        self.tools[tool_id] = updated
        return updated

    def create_action(self, workspace_id: UUID, request: ActionRequestCreate) -> ActionRequestView:
        if (request.connector, request.operation) not in ALLOWED_ACTIONS:
            raise HTTPException(status_code=422, detail="Operation is not allowlisted for MVP.")
        action = ActionRequestView(
            id=uuid4(), workspace_id=workspace_id, work_item_ids=request.work_item_ids,
            connector=request.connector, operation=request.operation, status="pending_confirmation",
            expires_at=now_utc() + timedelta(minutes=15), idempotency_key=uuid4(),
        )
        self.actions[action.id] = action
        return action

    def confirm_action(self, workspace_id: UUID, action_id: UUID) -> ActionRequestView:
        action = self._action_for_workspace(workspace_id, action_id)
        if action.expires_at <= now_utc():
            raise HTTPException(status_code=409, detail="Action request has expired.")
        if action.status != "pending_confirmation":
            raise HTTPException(status_code=409, detail="Action request cannot be confirmed in its current state.")
        action = action.model_copy(update={"status": "confirmed"})
        self.actions[action_id] = action
        return action

    def execute_action(self, workspace_id: UUID, action_id: UUID) -> ActionRequestView:
        action = self._action_for_workspace(workspace_id, action_id)
        if action.expires_at <= now_utc() or action.status != "confirmed":
            raise HTTPException(status_code=409, detail="A matching unexpired confirmation is required.")
        action = action.model_copy(update={"status": "executed"})
        self.actions[action_id] = action
        return action

    def _action_for_workspace(self, workspace_id: UUID, action_id: UUID) -> ActionRequestView:
        action = self.actions.get(action_id)
        if action is None or action.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Action request not found.")
        return action

    @staticmethod
    def analyze(evidence_ids: list[str]) -> list[Finding]:
        return [Finding(category="insufficient_evidence", confidence=0.0, evidence_ids=evidence_ids,
                        recommendation="Collect additional normalized source evidence.", approval_required=True)]
