"""Workflow CRUD, validation and execution through the public API."""

from __future__ import annotations

from conftest import API


def _graph_with(nodes, edges):
    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 1}}


def test_default_graph_and_crud(client, user, make_workflow):
    workflow = make_workflow(name="Fluxo padrão")
    assert workflow["version"] == 1
    assert workflow["is_active"] is True
    assert workflow["trigger_types"] == ["trigger_manual"]
    assert len(workflow["graph"]["nodes"]) == 2
    assert len(workflow["graph"]["edges"]) == 1

    listing = client.get(f"{API}/workflows", headers=user["headers"])
    assert listing.status_code == 200
    assert any(item["id"] == workflow["id"] for item in listing.json())

    fetched = client.get(f"{API}/workflows/{workflow['id']}", headers=user["headers"])
    assert fetched.status_code == 200
    assert fetched.json()["webhook_url"] is None

    renamed = client.patch(
        f"{API}/workflows/{workflow['id']}",
        json={"name": "Fluxo renomeado", "description": "Descrição"},
        headers=user["headers"],
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Fluxo renomeado"

    duplicated = client.post(
        f"{API}/workflows/{workflow['id']}/duplicate",
        json={"name": "Cópia"},
        headers=user["headers"],
    )
    assert duplicated.status_code == 201
    assert duplicated.json()["name"] == "Cópia"

    assert (
        client.delete(f"{API}/workflows/{workflow['id']}", headers=user["headers"]).status_code
        == 204
    )
    assert (
        client.get(f"{API}/workflows/{workflow['id']}", headers=user["headers"]).status_code
        == 404
    )


def test_validate_flags_missing_trigger_and_cycles(client, user):
    graph = _graph_with(
        [
            {
                "id": "a",
                "type": "action_set_data",
                "config": {"fields": {"valor": 1}},
            },
            {
                "id": "b",
                "type": "action_set_data",
                "config": {"fields": {"valor": 2}},
            },
        ],
        [
            {"id": "a-b", "source": "a", "target": "b"},
            {"id": "b-a", "source": "b", "target": "a"},
        ],
    )
    validation = client.post(
        f"{API}/workflows/validate",
        json=graph,
        headers=user["headers"],
    )
    assert validation.status_code == 200
    body = validation.json()
    assert body["valid"] is False
    messages = " ".join(issue["message"] for issue in body["issues"]).lower()
    assert "gatilho" in messages or "trigger" in messages
    assert "ciclo" in messages or "cycle" in messages or "laço" in messages


def test_manual_run_executes_and_logs(client, user, make_workflow, wait_execution):
    workflow = make_workflow()
    response = client.post(
        f"{API}/workflows/{workflow['id']}/run",
        json={"input": {"cliente": "Ana", "pedido": 42}},
        headers=user["headers"],
    )
    assert response.status_code == 202
    execution = response.json()
    assert execution["status"] in {"pending", "queued", "running"}

    detail = wait_execution(execution["id"])
    assert detail["status"] == "success", detail
    assert detail["workflow_id"] == workflow["id"]
    assert detail["steps"] >= 2
    assert detail["duration_ms"] is not None
    statuses = [log["status"] for log in detail["logs"]]
    assert "success" in statuses
    assert any(log["node_id"] for log in detail["logs"])

    history = client.get(
        f"{API}/executions?workflow_id={workflow['id']}", headers=user["headers"]
    )
    assert history.status_code == 200
    payload = history.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["workflow_name"] == workflow["name"]

    stats = client.get(f"{API}/workflows/{workflow['id']}/stats", headers=user["headers"])
    assert stats.status_code == 200
    assert stats.json()["total"] >= 1


def test_disabled_node_is_skipped(client, user, make_workflow, wait_execution):
    graph = _graph_with(
        [
            {
                "id": "start",
                "type": "trigger_manual",
                "config": {},
            },
            {
                "id": "middle",
                "type": "action_set_data",
                "config": {"fields": {"a": 1}},
                "disabled": True,
            },
            {
                "id": "end",
                "type": "action_set_data",
                "config": {"fields": {"valor": "{{ nodes.middle.a }}"}},
            },
        ],
        [
            {"id": "e1", "source": "start", "target": "middle"},
            {"id": "e2", "source": "middle", "target": "end"},
        ],
    )
    workflow = make_workflow(graph=graph)
    run = client.post(
        f"{API}/workflows/{workflow['id']}/run", json={}, headers=user["headers"]
    )
    assert run.status_code == 202
    detail = wait_execution(run.json()["id"])
    assert detail["status"] == "success", detail
    by_node = {log["node_id"]: log for log in detail["logs"]}
    assert by_node["middle"]["status"] == "skipped"
    assert by_node["end"]["status"] == "success"


def test_workflow_versions_snapshot_and_restore(client, user, make_workflow):
    workflow = make_workflow()
    workflow_id = workflow["id"]
    original_label = workflow["graph"]["nodes"][0]["label"]

    versions = client.get(
        f"{API}/workflows/{workflow_id}/versions", headers=user["headers"]
    )
    assert versions.status_code == 200, versions.text
    assert [item["version"] for item in versions.json()] == [1]
    assert versions.json()[0]["origin"] == "create"

    graph = workflow["graph"]
    graph["nodes"][0]["label"] = "Início alterado"
    updated = client.patch(
        f"{API}/workflows/{workflow_id}",
        json={"graph": graph},
        headers=user["headers"],
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2

    versions = client.get(
        f"{API}/workflows/{workflow_id}/versions", headers=user["headers"]
    )
    assert [item["version"] for item in versions.json()] == [2, 1]

    detail = client.get(
        f"{API}/workflows/{workflow_id}/versions/1", headers=user["headers"]
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["graph"]["nodes"][0]["label"] == original_label

    restored = client.post(
        f"{API}/workflows/{workflow_id}/versions/1/restore", headers=user["headers"]
    )
    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert body["version"] == 3
    assert body["graph"]["nodes"][0]["label"] == original_label

    versions = client.get(
        f"{API}/workflows/{workflow_id}/versions", headers=user["headers"]
    )
    assert [item["version"] for item in versions.json()] == [3, 2, 1]
    assert versions.json()[0]["origin"] == "restore"


def test_execution_not_found_for_other_user(client, make_workflow, user):

    workflow = make_workflow()
    response = client.post(
        f"{API}/workflows/{workflow['id']}/run", json={}, headers=user["headers"]
    )
    execution_id = response.json()["id"]

    other_email = f"other-{workflow['id']}@nexustest.com"
    client.post(
        f"{API}/auth/register",
        json={"name": "Outra Pessoa", "email": other_email, "password": "SenhaSegura123!"},
    )
    login = client.post(
        f"{API}/auth/login", json={"email": other_email, "password": "SenhaSegura123!"}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (
        client.get(f"{API}/executions/{execution_id}", headers=other_headers).status_code
        == 404
    )


