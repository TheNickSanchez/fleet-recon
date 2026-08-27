from __future__ import annotations

from uuid import UUID

from fastapi import Depends, FastAPI, File, UploadFile, status

from .schemas import ActionRequestCreate, ActionRequestView, RunRequest, RunSummary, ToolConfigPatch, ToolConfigView
from .security import Actor, authorize_workspace, current_actor, require_administrator
from .services import FleetReconService

app = FastAPI(title="Fleet Recon API", version="0.1.0")
service = FleetReconService()


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/v1/ready")
def ready() -> dict[str, str]:
    return {"status": "ready", "persistence": "in_memory_mvp"}


@app.post("/api/v1/workspaces/{workspace_id}/runs", response_model=RunSummary, status_code=status.HTTP_202_ACCEPTED)
def create_run(workspace_id: UUID, request: RunRequest, actor: Actor = Depends(authorize_workspace)) -> RunSummary:
    return service.create_run(workspace_id, request, actor)


@app.post("/api/v1/workspaces/{workspace_id}/runs/upload", response_model=RunSummary, status_code=status.HTTP_202_ACCEPTED)
async def upload_run(workspace_id: UUID, file: UploadFile = File(...), actor: Actor = Depends(authorize_workspace)) -> RunSummary:
    if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="Only CSV uploads are accepted.")
    return service.create_csv_run(workspace_id, await file.read(), actor)


@app.get("/api/v1/workspaces/{workspace_id}/runs/{run_id}", response_model=RunSummary)
def get_run(workspace_id: UUID, run_id: UUID, _: Actor = Depends(authorize_workspace)) -> RunSummary:
    return service.get_run(workspace_id, run_id)


@app.get("/api/v1/workspaces/{workspace_id}/admin/tools", response_model=list[ToolConfigView])
def list_tools(workspace_id: UUID, _: Actor = Depends(require_administrator)) -> list[ToolConfigView]:
    return list(service.tools.values())


@app.patch("/api/v1/workspaces/{workspace_id}/admin/tools/{tool_id}", response_model=ToolConfigView)
def update_tool(workspace_id: UUID, tool_id: str, patch: ToolConfigPatch, _: Actor = Depends(require_administrator)) -> ToolConfigView:
    return service.update_tool(tool_id, patch)


@app.post("/api/v1/workspaces/{workspace_id}/action-requests", response_model=ActionRequestView, status_code=status.HTTP_201_CREATED)
def create_action(workspace_id: UUID, request: ActionRequestCreate, _: Actor = Depends(authorize_workspace)) -> ActionRequestView:
    return service.create_action(workspace_id, request)


@app.post("/api/v1/workspaces/{workspace_id}/action-requests/{action_id}/confirm", response_model=ActionRequestView)
def confirm_action(workspace_id: UUID, action_id: UUID, _: Actor = Depends(authorize_workspace)) -> ActionRequestView:
    return service.confirm_action(workspace_id, action_id)


@app.post("/api/v1/workspaces/{workspace_id}/action-requests/{action_id}/execute", response_model=ActionRequestView)
def execute_action(workspace_id: UUID, action_id: UUID, _: Actor = Depends(authorize_workspace)) -> ActionRequestView:
    return service.execute_action(workspace_id, action_id)
