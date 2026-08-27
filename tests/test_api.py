from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import app, service

client = TestClient(app)


def setup_function() -> None:
    service.runs.clear()
    service.actions.clear()


def test_five_unique_users_route_to_micro_query() -> None:
    response = client.post(f"/api/v1/workspaces/{uuid4()}/runs", json={"input_kind": "pasted", "text": "Alice alice bob carol dave eve"})
    assert response.status_code == 202
    assert response.json()["input_count"] == 5
    assert response.json()["mode"] == "micro_query"


def test_six_users_and_csv_route_to_batch() -> None:
    workspace_id = uuid4()
    response = client.post(f"/api/v1/workspaces/{workspace_id}/runs", json={"input_kind": "typed", "text": "a b c d e f"})
    assert response.json()["mode"] == "batch_automation"
    response = client.post(f"/api/v1/workspaces/{workspace_id}/runs/upload", files={"file": ("users.csv", b"username\nalice\n", "text/csv")})
    assert response.status_code == 202
    assert response.json()["mode"] == "batch_automation"


def test_invalid_input_is_rejected() -> None:
    response = client.post(f"/api/v1/workspaces/{uuid4()}/runs", json={"input_kind": "typed", "text": "\u0000 ###"})
    assert response.status_code == 422


def test_tool_administration_requires_administrator() -> None:
    response = client.get(f"/api/v1/workspaces/{uuid4()}/admin/tools")
    assert response.status_code == 403
    response = client.get(f"/api/v1/workspaces/{uuid4()}/admin/tools", headers={"X-Role": "administrator"})
    assert response.status_code == 200


def test_action_cannot_execute_before_confirmation() -> None:
    workspace_id = uuid4()
    action = client.post(f"/api/v1/workspaces/{workspace_id}/action-requests", json={
        "work_item_ids": [str(uuid4())], "connector": "jamf", "operation": "trigger_policy",
    }).json()
    response = client.post(f"/api/v1/workspaces/{workspace_id}/action-requests/{action['id']}/execute")
    assert response.status_code == 409
    client.post(f"/api/v1/workspaces/{workspace_id}/action-requests/{action['id']}/confirm")
    response = client.post(f"/api/v1/workspaces/{workspace_id}/action-requests/{action['id']}/execute")
    assert response.status_code == 200
    assert response.json()["status"] == "executed"
