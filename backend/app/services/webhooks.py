"""Inbound webhook and event handling with secret/signature verification."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.core.security import decrypt_json, encrypt_json, generate_secret
from app.models.execution import WorkflowExecution
from app.models.workflow import Workflow
from app.services.executions import create_execution
from app.services.workflow_service import redact_graph, webhook_url


def _node_secret(node: dict[str, Any]) -> str | None:
    config = node.get("config") or {}
    encrypted = config.get("secret_encrypted")
    if not encrypted:
        return None
    try:
        return decrypt_json(encrypted).decode("utf-8")
    except Exception:
        return None


def find_trigger_node(
    workflow: Workflow, node_type: str, node_id: str | None = None
) -> dict[str, Any]:
    nodes = [
        node
        for node in (workflow.graph or {}).get("nodes", [])
        if node.get("type") == node_type and not node.get("disabled")
    ]
    if node_id:
        nodes = [node for node in nodes if node.get("id") == node_id]
    if not nodes:
        raise NotFoundError("Gatilho não encontrado para este workflow.")
    return nodes[0]


def verify_webhook_secret(
    node: dict[str, Any], headers: dict[str, str], body: bytes
) -> bool:
    secret = _node_secret(node)
    if not secret:
        return False
    config = node.get("config") or {}

    if config.get("require_signature"):
        timestamp = headers.get("x-nexus-timestamp", "")
        signature = headers.get("x-nexus-signature", "")
        if not timestamp or not signature:
            return False
        try:
            drift = abs(time.time() - int(timestamp))
        except ValueError:
            return False
        if drift > settings.webhook_signature_tolerance_seconds:
            return False
        message = timestamp.encode("utf-8") + b"." + body
        expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        provided = signature.strip()
        if provided.startswith("sha256="):
            provided = provided[len("sha256=") :]
        return hmac.compare_digest(expected, provided)

    provided_secret = headers.get("x-webhook-secret", "")
    return bool(provided_secret) and hmac.compare_digest(provided_secret, secret)


def handle_webhook(
    db: Session,
    *,
    workflow_id: int,
    method: str,
    headers: dict[str, str],
    body: bytes,
    payload: Any,
    query: dict[str, str],
) -> WorkflowExecution:
    workflow = db.scalar(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.is_active.is_(True))
    )
    if workflow is None:
        raise NotFoundError("Webhook não encontrado.")
    node = find_trigger_node(workflow, "trigger_webhook")
    expected_method = ((node.get("config") or {}).get("method") or "POST").upper()
    if method.upper() != expected_method:
        raise ValidationError(f"Este webhook aceita apenas {expected_method}.")
    if not verify_webhook_secret(node, headers, body):
        raise PermissionDeniedError("Segredo do webhook inválido.")

    return create_execution(
        db,
        workflow=workflow,
        trigger="webhook",
        trigger_data={
            "node_id": node["id"],
            "body": payload,
            "headers": {
                key: value
                for key, value in headers.items()
                if key.lower() not in {"authorization", "cookie", "x-webhook-secret", "x-nexus-signature"}
            },
            "query": query,
            "source_ip": headers.get("x-forwarded-for", ""),
        },
        input_data=payload if isinstance(payload, dict) else {"payload": payload},
        dedupe_active=settings.max_active_executions_per_workflow > 0,
    )


def handle_event(
    db: Session,
    *,
    topic: str,
    headers: dict[str, str],
    payload: Any,
) -> list[WorkflowExecution]:
    provided_secret = headers.get("x-event-secret", "")
    if not provided_secret:
        raise PermissionDeniedError("Cabeçalho X-Event-Secret é obrigatório.")

    workflows = db.scalars(
        select(Workflow).where(Workflow.is_active.is_(True))
    ).all()

    created: list[WorkflowExecution] = []
    for workflow in workflows:
        for node in (workflow.graph or {}).get("nodes", []):
            if node.get("type") != "trigger_event" or node.get("disabled"):
                continue
            config = node.get("config") or {}
            if (config.get("topic") or "") != topic:
                continue
            secret = _node_secret(node)
            if not secret or not hmac.compare_digest(provided_secret, secret):
                continue
            created.append(
                create_execution(
                    db,
                    workflow=workflow,
                    trigger="event",
                    trigger_data={"node_id": node["id"], "body": payload, "topic": topic},
                    input_data=payload if isinstance(payload, dict) else {"payload": payload},
                )
            )
            break

    if not created:
        raise NotFoundError("Nenhum workflow ativo inscrito neste evento.")
    return created


def rotate_webhook_secret(
    db: Session, *, workflow: Workflow, node_id: str | None = None, node_type: str = "trigger_webhook"
) -> dict[str, Any]:
    node = find_trigger_node(workflow, node_type, node_id)
    secret = generate_secret(24)
    graph = dict(workflow.graph or {})
    nodes = []
    for item in graph.get("nodes", []):
        if item.get("id") == node["id"]:
            item = {**item, "config": {**(item.get("config") or {})}}
            item["config"]["secret_encrypted"] = encrypt_json(secret.encode("utf-8"))
            item["config"]["secret_configured"] = True
        nodes.append(item)
    graph["nodes"] = nodes
    workflow.graph = graph
    db.commit()
    db.refresh(workflow)

    return {
        "secret": secret,
        "node_id": node["id"],
        "url": webhook_url(workflow.id) if node_type == "trigger_webhook" else None,
        "signature_header": "X-Nexus-Signature",
        "timestamp_header": "X-Nexus-Timestamp",
        "graph": redact_graph(workflow.graph),
    }


def webhook_info(db: Session, workflow: Workflow) -> dict[str, Any]:
    nodes = [
        node
        for node in (workflow.graph or {}).get("nodes", [])
        if node.get("type") == "trigger_webhook" and not node.get("disabled")
    ]
    if not nodes:
        return {"configured": False, "url": None, "node_id": None, "secret_configured": False}
    node = nodes[0]
    config = node.get("config") or {}
    return {
        "configured": bool(config.get("secret_encrypted")),
        "url": webhook_url(workflow.id) if workflow.is_active else None,
        "node_id": node["id"],
        "method": config.get("method", "POST"),
        "secret_configured": bool(config.get("secret_encrypted")),
        "require_signature": bool(config.get("require_signature")),
    }
