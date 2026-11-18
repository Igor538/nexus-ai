"""Public webhook and event ingestion endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ValidationError
from app.core.rate_limit import limiter
from app.services.webhooks import handle_event, handle_webhook

router = APIRouter()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _read_body(request: Request) -> tuple[bytes, object]:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.webhook_max_body_bytes:
        raise ValidationError("Corpo da requisição excede o limite permitido.")
    body = await request.body()
    if len(body) > settings.webhook_max_body_bytes:
        raise ValidationError("Corpo da requisição excede o limite permitido.")
    if not body:
        return body, {}
    content_type = request.headers.get("content-type", "")
    if "json" in content_type or body[:1] in {b"{", b"["}:
        try:
            return body, json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValidationError("Corpo JSON inválido.") from exc
    try:
        return body, {"raw": body.decode("utf-8")}
    except UnicodeDecodeError:
        return body, {"raw_base64": __import__("base64").b64encode(body).decode("ascii")}


@router.api_route(
    "/{workflow_id}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=True,
)
async def receive_webhook(workflow_id: int, request: Request, db: Session = Depends(get_db)):
    limiter.hit(
        "webhook", f"{workflow_id}:{_client_ip(request)}", settings.webhook_rate_limit_per_minute
    )
    body, payload = await _read_body(request)
    headers = {key.lower(): value for key, value in request.headers.items()}
    execution = handle_webhook(
        db,
        workflow_id=workflow_id,
        method=request.method,
        headers=headers,
        body=body,
        payload=payload,
        query=dict(request.query_params),
    )
    return {
        "status": "accepted",
        "execution_id": execution.id,
        "message": "Workflow disparado com sucesso.",
    }


@router.post("/events/{topic}")
async def receive_event(topic: str, request: Request, db: Session = Depends(get_db)):
    limiter.hit(
        "event", f"{topic}:{_client_ip(request)}", settings.webhook_rate_limit_per_minute
    )
    body, payload = await _read_body(request)
    headers = {key.lower(): value for key, value in request.headers.items()}
    executions = handle_event(db, topic=topic, headers=headers, payload=payload)
    return {
        "status": "accepted",
        "executions": [{"id": item.id, "workflow_id": item.workflow_id} for item in executions],
    }
