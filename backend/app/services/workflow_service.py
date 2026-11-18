"""Workflow graph normalization, validation, redaction and schedule sync."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.core.security import encrypt_json
from app.models.schedule import ScheduledTask
from app.models.user import User
from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.workflow import Graph
from app.services.ai.registry import resolve_api_key
from app.services.nodes import all_nodes
from app.services.nodes.registry import trigger_types

MAX_NODES = 100
MAX_EDGES = 300


def empty_graph() -> dict[str, Any]:
    return {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}


def default_graph() -> dict[str, Any]:
    trigger_id = f"trigger_{uuid.uuid4().hex[:8]}"
    action_id = f"action_{uuid.uuid4().hex[:8]}"
    return {
        "nodes": [
            {
                "id": trigger_id,
                "type": "trigger_manual",
                "label": "Execução manual",
                "position": {"x": 60, "y": 160},
                "config": {},
            },
            {
                "id": action_id,
                "type": "action_notification",
                "label": "Notificar conclusão",
                "position": {"x": 380, "y": 160},
                "config": {
                    "channel": "internal",
                    "title": "Workflow executado",
                    "message": "Entrada recebida: {{ input }}",
                    "level": "success",
                },
            },
        ],
        "edges": [
            {
                "id": f"edge_{uuid.uuid4().hex[:8]}",
                "source": trigger_id,
                "target": action_id,
                "sourceHandle": "default",
                "targetHandle": None,
            }
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def ensure_owned_workflow(db: Session, user_id: int, workflow_id: int) -> Workflow:
    workflow = db.scalar(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == user_id)
    )
    if workflow is None:
        raise NotFoundError("Workflow não encontrado.")
    return workflow


def normalize_graph(
    graph: Graph, *, existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate the graph shape and move webhook secrets into hashed storage."""
    existing = existing or empty_graph()
    existing_nodes = {node.get("id"): node for node in existing.get("nodes", [])}
    payload = graph.model_dump()
    payload["viewport"] = payload.get("viewport") or {"x": 0, "y": 0, "zoom": 1}

    for node in payload["nodes"]:
        config = dict(node.get("config") or {})
        if node["type"] in {"trigger_webhook", "trigger_event"}:
            plain_secret = config.pop("secret", None)
            config.pop("secret_hash", None)
            previous = existing_nodes.get(node["id"]) or {}
            previous_secret = (previous.get("config") or {}).get("secret_encrypted")
            config.pop("secret_encrypted", None)
            if isinstance(plain_secret, str) and plain_secret.strip():
                config["secret_encrypted"] = encrypt_json(plain_secret.strip().encode("utf-8"))
                config["secret_configured"] = True
            elif previous_secret:
                config["secret_encrypted"] = previous_secret
                config["secret_configured"] = True
            else:
                config["secret_configured"] = False
        node["config"] = config

    return payload


def redact_graph(graph: dict[str, Any] | None) -> dict[str, Any]:
    safe = copy.deepcopy(graph or empty_graph())
    for node in safe.get("nodes", []):
        config = node.get("config") or {}
        if "secret_encrypted" in config or "secret_hash" in config:
            config.pop("secret_encrypted", None)
            config.pop("secret_hash", None)
            config["secret_configured"] = True
        config.pop("secret", None)
    return safe


def snapshot_workflow_version(
    db: Session,
    workflow: Workflow,
    *,
    graph: dict[str, Any] | None = None,
    origin: str = "manual",
    created_by: int | None = None,
) -> WorkflowVersion:
    """Store an immutable, secret-free snapshot of the current workflow version."""
    snapshot = WorkflowVersion(
        workflow_id=workflow.id,
        version=workflow.version,
        name=workflow.name,
        description=workflow.description,
        graph=redact_graph(graph if graph is not None else workflow.graph),
        origin=origin,
        created_by=created_by,
    )
    db.add(snapshot)
    return snapshot


def version_summary(version: WorkflowVersion) -> dict[str, Any]:
    graph = version.graph or empty_graph()
    return {
        "id": version.id,
        "workflow_id": version.workflow_id,
        "version": version.version,
        "name": version.name,
        "description": version.description,
        "origin": version.origin,
        "created_by": version.created_by,
        "created_at": version.created_at,
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
    }


def graph_trigger_types(graph: dict[str, Any] | None) -> list[str]:
    if not graph:
        return []
    kinds = {
        node.get("type")
        for node in graph.get("nodes", [])
        if node.get("type") in trigger_types()
    }
    return sorted(kind for kind in kinds if kind)


def graph_summary(graph: dict[str, Any] | None) -> dict[str, Any]:
    graph = graph or empty_graph()
    return {
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
        "trigger_types": graph_trigger_types(graph),
    }


def webhook_url(workflow_id: int) -> str:
    return f"{settings.webhook_base_url.rstrip('/')}{settings.api_v1_prefix}/webhooks/{workflow_id}"


def schedule_cron(graph: dict[str, Any] | None) -> str | None:
    for node in (graph or {}).get("nodes", []):
        if node.get("type") == "trigger_schedule":
            return (node.get("config") or {}).get("cron")
    return None


def validate_graph(
    db: Session,
    *,
    user_id: int,
    graph: dict[str, Any],
    is_active: bool = False,
    workflow_id: int | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    registry = all_nodes()

    def add(message: str, node_id: str | None = None, severity: str = "error") -> None:
        issues.append({"severity": severity, "node_id": node_id, "message": message})

    if not nodes:
        add("O workflow não possui nenhum nó.")
        return issues
    if len(nodes) > MAX_NODES:
        add(f"O workflow excede o limite de {MAX_NODES} nós.")
    if len(edges) > MAX_EDGES:
        add(f"O workflow excede o limite de {MAX_EDGES} conexões.")

    node_ids: set[str] = set()
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            add("Existe um nó sem identificador.")
            continue
        if node_id in node_ids:
            add("Identificador de nó duplicado.", node_id)
        node_ids.add(node_id)
        node_type = node.get("type")
        implementation = registry.get(node_type)
        if implementation is None:
            add(f"Tipo de nó desconhecido: {node_type}", node_id)
            continue
        try:
            implementation.config_model(**(node.get("config") or {}))
        except Exception as exc:
            add(f"Configuração inválida: {_short_error(exc)}", node_id)

    edge_ids: set[str] = set()
    targets: dict[str, list[str]] = {}
    sources: dict[str, list[str]] = {}
    for edge in edges:
        edge_id = edge.get("id")
        if not edge_id:
            add("Existe uma conexão sem identificador.")
            continue
        if edge_id in edge_ids:
            add("Identificador de conexão duplicado.", edge.get("source"))
        edge_ids.add(edge_id)
        source, target = edge.get("source"), edge.get("target")
        if source not in node_ids or target not in node_ids:
            add("Conexão aponta para um nó inexistente.", source)
            continue
        if source == target:
            add("Um nó não pode se conectar a si mesmo.", source)
            continue
        sources.setdefault(target, []).append(source)
        targets.setdefault(source, []).append(target)

    if _has_cycle(node_ids, edges):
        add("O workflow contém um ciclo. Use o nó Loop em vez de conexões circulares.")

    triggers = [
        node
        for node in nodes
        if node.get("type") in trigger_types() and not node.get("disabled")
    ]
    if not triggers:
        add("O workflow não possui um nó de gatilho.")
    elif is_active and len(triggers) == 0:
        add("Um workflow ativo precisa de pelo menos um gatilho.")

    if triggers:
        reachable = _reachable({node["id"] for node in triggers}, targets)
        for node in nodes:
            if node.get("id") not in reachable and not node.get("disabled"):
                add(
                    "Este nó não é alcançável a partir de nenhum gatilho.",
                    node.get("id"),
                    severity="warning",
                )

    for node in nodes:
        if node.get("type") == "logic_switch":
            config = node.get("config") or {}
            case_ids = [case.get("id") for case in config.get("cases") or []]
            if len(case_ids) != len(set(case_ids)):
                add("Os casos do Switch precisam de identificadores únicos.", node.get("id"))
            if any(case_id == config.get("default_label") for case_id in case_ids):
                add("O rótulo padrão do Switch não pode repetir um caso.", node.get("id"))
        if node.get("type") == "logic_loop":
            loop_workflow_id = (node.get("config") or {}).get("workflow_id")
            if loop_workflow_id:
                if workflow_id == loop_workflow_id:
                    add("O Loop não pode executar o próprio workflow.", node.get("id"))
                else:
                    exists = db.scalar(
                        select(Workflow.id).where(
                            Workflow.id == loop_workflow_id, Workflow.user_id == user_id
                        )
                    )
                    if not exists:
                        add(
                            "O sub-workflow do Loop não existe ou não pertence a você.",
                            node.get("id"),
                        )
        if node.get("type") == "trigger_webhook":
            config = node.get("config") or {}
            if config.get("require_signature") and not (
                config.get("secret_encrypted") or config.get("secret")
            ):
                add(
                    "O webhook exige assinatura, mas nenhum segredo foi configurado. "
                    "Gere o segredo na aba de webhook.",
                    node.get("id"),
                    severity="warning",
                )
        if node.get("type") in {"ai_chat", "ai_agent", "ai_classify", "ai_extract", "ai_summarize"}:
            config = node.get("config") or {}
            provider = (config.get("provider") or settings.ai_default_provider).lower()
            if provider != "ollama" and not resolve_api_key(provider):
                add(
                    f"Nenhuma chave de API configurada para o provedor '{provider}'. "
                    "A execução falhará até que a chave seja configurada.",
                    node.get("id"),
                    severity="warning",
                )

    return issues


def _short_error(exc: Exception) -> str:
    if hasattr(exc, "errors"):
        try:
            errors = exc.errors()  # type: ignore[attr-defined]
            parts = []
            for error in errors[:3]:
                loc = ".".join(str(item) for item in error.get("loc", []))
                parts.append(f"{loc}: {error.get('msg')}" if loc else str(error.get("msg")))
            return "; ".join(parts) or str(exc)
        except Exception:
            return str(exc)
    return str(exc)


def _has_cycle(node_ids: set[str], edges: list[dict[str, Any]]) -> bool:
    indegree = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in node_ids and target in node_ids:
            adjacency[source].append(target)
            indegree[target] += 1
    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for neighbor in adjacency[current]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)
    return visited != len(node_ids)


def _reachable(starts: set[str], adjacency: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(starts)
    while stack:
        current = stack.pop()
        if current in seen or current not in adjacency and current not in starts:
            continue
        seen.add(current)
        stack.extend(adjacency.get(current, []))
    return seen


def sync_schedules(db: Session, workflow: Workflow) -> None:
    nodes = {
        node["id"]: node
        for node in (workflow.graph or {}).get("nodes", [])
        if node.get("type") == "trigger_schedule"
    }
    existing = {
        task.node_id: task
        for task in db.scalars(
            select(ScheduledTask).where(ScheduledTask.workflow_id == workflow.id)
        ).all()
    }

    for node_id in list(existing):
        if node_id not in nodes:
            db.delete(existing[node_id])

    now = datetime.now(timezone.utc)
    for node_id, node in nodes.items():
        config = node.get("config") or {}
        cron = config.get("cron") or ""
        timezone_name = config.get("timezone") or "UTC"
        if not croniter.is_valid(cron):
            continue
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = timezone.utc
        next_run = _next_run(cron, now.astimezone(tz)).astimezone(timezone.utc)
        task = existing.get(node_id)
        if task is None:
            task = ScheduledTask(
                workflow_id=workflow.id,
                node_id=node_id,
                cron=cron,
                timezone=timezone_name,
                next_run_at=next_run,
                is_active=workflow.is_active,
            )
            db.add(task)
        else:
            if task.cron != cron or task.timezone != timezone_name:
                task.next_run_at = next_run
            task.cron = cron
            task.timezone = timezone_name
            task.is_active = workflow.is_active
    db.commit()


def _next_run(cron: str, base: datetime) -> datetime:
    return croniter(cron, base).get_next(datetime)


def upcoming_schedules(db: Session, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ScheduledTask, Workflow.name)
        .join(Workflow, Workflow.id == ScheduledTask.workflow_id)
        .where(Workflow.user_id == user_id, ScheduledTask.is_active.is_(True))
        .order_by(ScheduledTask.next_run_at.asc())
        .limit(limit)
    ).all()
    return [
        {
            "id": task.id,
            "workflow_id": task.workflow_id,
            "workflow_name": workflow_name,
            "node_id": task.node_id,
            "cron": task.cron,
            "timezone": task.timezone,
            "next_run_at": task.next_run_at,
            "last_run_at": task.last_run_at,
        }
        for task, workflow_name in rows
    ]


def validate_owned_user(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise ValidationError("Usuário inválido.")
    return user
