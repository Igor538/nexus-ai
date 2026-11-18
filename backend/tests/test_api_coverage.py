"""Coverage for auxiliary API surfaces: health, catalog, credentials, AI,
notifications, dashboard and execution retry/cancel."""

from __future__ import annotations

from conftest import API

from app.models.execution import WorkflowExecution


def _graph_with(nodes, edges):
    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 1}}


def test_health_catalog_and_ai_metadata(client, user):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    database = client.get("/health/database")
    assert database.status_code == 200
    assert database.json()["status"] == "ok"

    catalog = client.get(f"{API}/nodes", headers=user["headers"])
    assert catalog.status_code == 200
    body = catalog.json()
    node_types = {entry["type"] for entry in body["nodes"]}
    assert {"trigger_manual", "action_notification", "action_set_data"} <= node_types
    assert body["categories"]

    providers = client.get(f"{API}/ai/providers", headers=user["headers"])
    assert providers.status_code == 200
    assert isinstance(providers.json()["providers"], list)

    usage = client.get(f"{API}/ai/usage?days=7", headers=user["headers"])
    assert usage.status_code == 200
    assert usage.json()["period_days"] == 7
    assert usage.json()["total_tokens"] >= 0


def test_credentials_crud_never_returns_secrets(client, user):
    types = client.get(f"{API}/credentials/types", headers=user["headers"])
    assert types.status_code == 200
    assert any(item["type"] == "http_bearer" for item in types.json()["types"])

    created = client.post(
        f"{API}/credentials",
        json={"name": "Token interno", "type": "http_bearer", "data": {"token": "segredo-123"}},
        headers=user["headers"],
    )
    assert created.status_code == 201, created.text
    credential = created.json()
    assert credential["fields"] == ["token"]
    assert "segredo-123" not in created.text

    listing = client.get(f"{API}/credentials", headers=user["headers"])
    assert listing.status_code == 200
    assert any(item["id"] == credential["id"] for item in listing.json())

    updated = client.patch(
        f"{API}/credentials/{credential['id']}",
        json={"name": "Token renomeado"},
        headers=user["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Token renomeado"

    invalid = client.post(
        f"{API}/credentials",
        json={"name": "Inválida", "type": "http_bearer", "data": {}},
        headers=user["headers"],
    )
    assert invalid.status_code == 422

    removed = client.delete(
        f"{API}/credentials/{credential['id']}", headers=user["headers"]
    )
    assert removed.status_code == 204
    assert client.get(f"{API}/credentials", headers=user["headers"]).json() == []


def test_internal_notification_and_dashboard(client, user, make_workflow, wait_execution):
    graph = _graph_with(
        [
            {"id": "start", "type": "trigger_manual", "config": {}},
            {
                "id": "notify",
                "type": "action_notification",
                "config": {
                    "channel": "internal",
                    "title": "Teste de notificação",
                    "message": "Execução concluída",
                    "level": "success",
                },
            },
        ],
        [{"id": "e1", "source": "start", "target": "notify"}],
    )
    workflow = make_workflow(graph=graph)
    run = client.post(
        f"{API}/workflows/{workflow['id']}/run", json={}, headers=user["headers"]
    )
    assert run.status_code == 202
    assert wait_execution(run.json()["id"])["status"] == "success"

    inbox = client.get(f"{API}/notifications?unread_only=true", headers=user["headers"])
    assert inbox.status_code == 200
    payload = inbox.json()
    assert payload["unread"] >= 1
    notification = payload["items"][0]
    assert notification["title"] == "Teste de notificação"
    assert notification["read"] is False

    read = client.post(
        f"{API}/notifications/{notification['id']}/read", headers=user["headers"]
    )
    assert read.status_code == 200
    assert read.json()["read"] is True

    read_all = client.post(f"{API}/notifications/read-all", headers=user["headers"])
    assert read_all.status_code == 200
    assert client.get(f"{API}/notifications", headers=user["headers"]).json()["unread"] == 0

    stats = client.get(f"{API}/dashboard/stats", headers=user["headers"])
    assert stats.status_code == 200
    body = stats.json()
    assert body["workflows"]["total"] >= 1
    assert body["executions"]["total"] >= 1
    assert body["recent_executions"]
    assert "tokens" in body["ai"]
    assert isinstance(body["daily"], list)


def test_execution_cancel_and_retry(client, user, make_workflow, wait_execution, db_session):
    workflow = make_workflow()
    pending = WorkflowExecution(
        workflow_id=workflow["id"],
        user_id=user["id"],
        status="pending",
        trigger="manual",
        trigger_data={},
        input={},
    )
    db_session.add(pending)
    db_session.commit()
    db_session.refresh(pending)

    cancelled = client.post(
        f"{API}/executions/{pending.id}/cancel", headers=user["headers"]
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["finished_at"] is not None

    run = client.post(
        f"{API}/workflows/{workflow['id']}/run", json={"input": {"x": 1}}, headers=user["headers"]
    )
    assert run.status_code == 202
    original = wait_execution(run.json()["id"])
    assert original["status"] == "success"

    retried = client.post(
        f"{API}/executions/{original['id']}/retry", headers=user["headers"]
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["trigger"] == "retry"

    replay = wait_execution(retried.json()["id"])
    assert replay["status"] == "success"
    assert replay["trigger_data"]["retried_from"] == original["id"]
    assert replay["input"] == {"x": 1}
