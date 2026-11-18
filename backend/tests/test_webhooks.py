"""Inbound webhook secrets, HMAC signatures and external events."""

from __future__ import annotations

import time

from conftest import API

from app.core.security import sign_payload


def _webhook_graph(require_signature: bool = False) -> dict:
    return {
        "nodes": [
            {
                "id": "hook",
                "type": "trigger_webhook",
                "config": {"method": "POST", "require_signature": require_signature},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "save",
                "type": "action_set_data",
                "config": {"fields": {"valor": "{{ trigger.body.value }}"}},
                "position": {"x": 260, "y": 0},
            },
        ],
        "edges": [{"id": "hook-save", "source": "hook", "target": "save"}],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def _event_graph() -> dict:
    return {
        "nodes": [
            {
                "id": "event",
                "type": "trigger_event",
                "config": {"topic": "pedidos.criados"},
            }
        ],
        "edges": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def test_webhook_requires_correct_secret(client, user, make_workflow, wait_execution):
    workflow = make_workflow(graph=_webhook_graph())
    info = client.get(f"{API}/workflows/{workflow['id']}/webhook", headers=user["headers"])
    assert info.status_code == 200
    assert info.json()["configured"] is False

    rotated = client.post(
        f"{API}/workflows/{workflow['id']}/webhook/rotate", headers=user["headers"]
    )
    assert rotated.status_code == 200
    secret = rotated.json()["secret"]
    assert secret
    assert "secret_encrypted" not in str(rotated.json()["graph"])

    info = client.get(f"{API}/workflows/{workflow['id']}/webhook", headers=user["headers"])
    assert info.json()["configured"] is True
    assert info.json()["secret_configured"] is True
    assert info.json()["url"].endswith(f"/webhooks/{workflow['id']}")

    denied = client.post(
        f"{API}/webhooks/{workflow['id']}",
        json={"value": 10},
        headers={"X-Webhook-Secret": "segredo-errado"},
    )
    assert denied.status_code == 403

    accepted = client.post(
        f"{API}/webhooks/{workflow['id']}",
        json={"value": 10},
        headers={"X-Webhook-Secret": secret},
    )
    assert accepted.status_code == 200, accepted.text
    execution = wait_execution(accepted.json()["execution_id"])
    assert execution["status"] == "success", execution
    assert execution["trigger"] == "webhook"
    saved = next(log for log in execution["logs"] if log["node_id"] == "save")
    assert saved["output"]["valor"] == 10


def test_webhook_hmac_signature(client, user, make_workflow, wait_execution):
    workflow = make_workflow(graph=_webhook_graph(require_signature=True))
    rotated = client.post(
        f"{API}/workflows/{workflow['id']}/webhook/rotate", headers=user["headers"]
    )
    secret = rotated.json()["secret"]

    body = b'{"value": "assinado"}'
    timestamp = str(int(time.time()))
    signature = sign_payload(secret, timestamp, body)

    invalid = client.post(
        f"{API}/webhooks/{workflow['id']}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Nexus-Timestamp": timestamp,
            "X-Nexus-Signature": "sha256=deadbeef",
        },
    )
    assert invalid.status_code == 403

    valid = client.post(
        f"{API}/webhooks/{workflow['id']}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Nexus-Timestamp": timestamp,
            "X-Nexus-Signature": f"sha256={signature}",
        },
    )
    assert valid.status_code == 200, valid.text
    execution = wait_execution(valid.json()["execution_id"])
    assert execution["status"] == "success", execution

    stale = client.post(
        f"{API}/webhooks/{workflow['id']}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Nexus-Timestamp": "1",
            "X-Nexus-Signature": f"sha256={sign_payload(secret, '1', body)}",
        },
    )
    assert stale.status_code == 403


def test_webhook_rejects_inactive_workflow(client, user, make_workflow):
    workflow = make_workflow(graph=_webhook_graph(), active=False)
    response = client.post(
        f"{API}/webhooks/{workflow['id']}",
        json={"value": 1},
        headers={"X-Webhook-Secret": "qualquer"},
    )
    assert response.status_code == 404


def test_external_event_dispatch(client, user, make_workflow, wait_execution):
    workflow = make_workflow(graph=_event_graph())
    rotated = client.post(
        f"{API}/workflows/{workflow['id']}/webhook/rotate",
        params={"node_type": "trigger_event"},
        headers=user["headers"],
    )
    assert rotated.status_code == 200, rotated.text
    secret = rotated.json()["secret"]

    missing = client.post(
        f"{API}/webhooks/events/pedidos.criados", json={"id": 1}
    )
    assert missing.status_code == 403

    unknown = client.post(
        f"{API}/webhooks/events/evento.inexistente",
        json={"id": 1},
        headers={"X-Event-Secret": secret},
    )
    assert unknown.status_code == 404

    response = client.post(
        f"{API}/webhooks/events/pedidos.criados",
        json={"id": 1, "total": 99},
        headers={"X-Event-Secret": secret},
    )
    assert response.status_code == 200, response.text
    created = response.json()["executions"]
    assert created and created[0]["workflow_id"] == workflow["id"]

    execution = wait_execution(created[0]["id"])
    assert execution["status"] == "success", execution


def test_webhook_body_limit(client, user, make_workflow):
    workflow = make_workflow(graph=_webhook_graph())
    rotated = client.post(
        f"{API}/workflows/{workflow['id']}/webhook/rotate", headers=user["headers"]
    )
    secret = rotated.json()["secret"]
    huge = {"blob": "x" * 300_000}
    response = client.post(
        f"{API}/webhooks/{workflow['id']}",
        json=huge,
        headers={"X-Webhook-Secret": secret},
    )
    assert response.status_code == 422

