"""Workflow CRUD, validation, manual runs and webhook management."""

from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import NotFoundError, ValidationError
from app.models.execution import WorkflowExecution
from app.models.user import User
from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.execution import ExecutionResponse, WorkflowRunRequest
from app.schemas.workflow import (
    Graph,
    WorkflowCreate,
    WorkflowDuplicateRequest,
    WorkflowGenerateRequest,
    WorkflowGenerateResponse,
    WorkflowResponse,
    WorkflowSummary,
    WorkflowUpdate,
    WorkflowValidationIssue,
    WorkflowValidationResponse,
    WorkflowVersionDetail,
    WorkflowVersionSummary,
)
from app.services.ai.generator import generate_workflow_graph
from app.services.executions import create_execution
from app.services.nodes import all_nodes
from app.services.nodes.registry import trigger_types
from app.services.webhooks import rotate_webhook_secret, webhook_info
from app.services.workflow_service import (
    default_graph,
    ensure_owned_workflow,
    graph_summary,
    normalize_graph,
    redact_graph,
    schedule_cron,
    snapshot_workflow_version,
    sync_schedules,
    validate_graph,
    version_summary,
    webhook_url,
)

router = APIRouter()


def _summary(workflow: Workflow) -> WorkflowSummary:
    data = WorkflowSummary.model_validate(workflow).model_dump()
    data.update(graph_summary(workflow.graph))
    return WorkflowSummary(**data)


def _response(workflow: Workflow) -> WorkflowResponse:
    redacted = redact_graph(workflow.graph)
    data = _summary(workflow).model_dump()
    has_webhook = any(
        node.get("type") == "trigger_webhook" for node in redacted.get("nodes", [])
    )
    return WorkflowResponse(
        **data,
        graph=Graph(**redacted),
        webhook_url=webhook_url(workflow.id) if workflow.is_active and has_webhook else None,
        schedule_cron=schedule_cron(redacted),
    )


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(
    search: str | None = Query(default=None, max_length=150),
    is_active: bool | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conditions = [Workflow.user_id == current_user.id]
    if search:
        conditions.append(Workflow.name.ilike(f"%{search.strip()}%"))
    if is_active is not None:
        conditions.append(Workflow.is_active.is_(is_active))

    workflows = db.scalars(
        select(Workflow)
        .where(*conditions)
        .order_by(Workflow.updated_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_summary(workflow) for workflow in workflows]


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    graph = payload.graph or Graph(**default_graph())
    normalized = normalize_graph(graph)
    workflow = Workflow(
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        user_id=current_user.id,
        graph=normalized,
        is_active=bool(normalized.get("nodes")),
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    snapshot_workflow_version(
        db, workflow, origin="create", created_by=current_user.id
    )
    db.commit()
    sync_schedules(db, workflow)
    return _response(workflow)


@router.post("/validate", response_model=WorkflowValidationResponse)
def validate_workflow_graph(
    graph: Graph,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    issues = validate_graph(
        db,
        user_id=current_user.id,
        graph=normalize_graph(graph),
        is_active=True,
    )
    return WorkflowValidationResponse(
        valid=not any(issue["severity"] == "error" for issue in issues),
        issues=[WorkflowValidationIssue(**issue) for issue in issues],
    )


@router.post("/generate", response_model=WorkflowGenerateResponse)
async def generate_workflow(
    payload: WorkflowGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await generate_workflow_graph(
        db,
        user_id=current_user.id,
        prompt=payload.prompt,
        provider_name=payload.provider,
        model=payload.model,
    )
    return WorkflowGenerateResponse(
        graph=Graph(**result["graph"]),
        issues=[WorkflowValidationIssue(**issue) for issue in result["issues"]],
        provider=result["provider"],
        model=result["model"],
        provider_label=result.get("provider_label"),
        explanation=result.get("explanation"),
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    return _response(workflow)


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(
    workflow_id: int,
    payload: WorkflowUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "name" in update_data:
        if not update_data["name"] or len(update_data["name"].strip()) < 2:
            raise ValidationError("O nome deve ter pelo menos 2 caracteres.")
        update_data["name"] = update_data["name"].strip()
    if "description" in update_data and update_data["description"] is not None:
        update_data["description"] = update_data["description"].strip() or None

    new_graph = None
    if payload.graph is not None:
        new_graph = normalize_graph(payload.graph, existing=workflow.graph)
        update_data.pop("graph", None)

    target_active = update_data.get("is_active", workflow.is_active)
    candidate_graph = new_graph if new_graph is not None else workflow.graph
    if target_active:
        issues = validate_graph(
            db,
            user_id=current_user.id,
            graph=candidate_graph,
            is_active=True,
            workflow_id=workflow.id,
        )
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            raise ValidationError(
                "O workflow possui problemas que impedem a ativação.",
                details={"issues": errors},
            )

    previous_version = workflow.version
    for field, value in update_data.items():
        setattr(workflow, field, value)
    if new_graph is not None:
        workflow.graph = new_graph
        workflow.version += 1
    if update_data.get("is_active") is True:
        workflow.version += 1

    db.commit()
    db.refresh(workflow)
    if workflow.version != previous_version:
        snapshot_workflow_version(
            db, workflow, origin="update", created_by=current_user.id
        )
        db.commit()
    sync_schedules(db, workflow)
    return _response(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    db.delete(workflow)
    db.commit()
    return None


@router.post(
    "/{workflow_id}/duplicate",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_workflow(
    workflow_id: int,
    payload: WorkflowDuplicateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    graph = copy.deepcopy(workflow.graph or {})
    for node in graph.get("nodes", []):
        config = node.get("config") or {}
        config.pop("secret_encrypted", None)
        config["secret_configured"] = False

    name = (payload.name if payload else None) or f"{workflow.name} (cópia)"
    clone = Workflow(
        name=name.strip()[:150],
        description=workflow.description,
        user_id=current_user.id,
        graph=graph,
        is_active=False,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    snapshot_workflow_version(
        db, clone, origin="duplicate", created_by=current_user.id
    )
    db.commit()
    return _response(clone)


@router.post("/{workflow_id}/validate", response_model=WorkflowValidationResponse)
def validate_saved_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    issues = validate_graph(
        db,
        user_id=current_user.id,
        graph=workflow.graph or {},
        is_active=workflow.is_active,
        workflow_id=workflow.id,
    )
    return WorkflowValidationResponse(
        valid=not any(issue["severity"] == "error" for issue in issues),
        issues=[WorkflowValidationIssue(**issue) for issue in issues],
    )


@router.post(
    "/{workflow_id}/run",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_workflow(
    workflow_id: int,
    payload: WorkflowRunRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    issues = validate_graph(
        db,
        user_id=current_user.id,
        graph=workflow.graph or {},
        is_active=False,
        workflow_id=workflow.id,
    )
    errors = [issue for issue in issues if issue["severity"] == "error"]
    if errors:
        raise ValidationError(
            "Corrija os problemas do workflow antes de executar.",
            details={"issues": errors},
        )

    trigger_node_id = payload.trigger_node_id if payload else None
    if trigger_node_id:
        node = next(
            (
                item
                for item in (workflow.graph or {}).get("nodes", [])
                if item.get("id") == trigger_node_id
                and item.get("type") in trigger_types()
            ),
            None,
        )
        if node is None:
            raise ValidationError("Nó de gatilho inválido para execução manual.")

    execution = create_execution(
        db,
        workflow=workflow,
        trigger="manual",
        trigger_data={"node_id": trigger_node_id},
        input_data=(payload.input if payload else {}) or {},
        dedupe_active=True,
    )
    return ExecutionResponse.model_validate(execution).model_copy(
        update={"workflow_name": workflow.name}
    )


@router.get("/{workflow_id}/webhook")
def get_workflow_webhook(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    return webhook_info(db, workflow)


@router.post("/{workflow_id}/webhook/rotate")
def rotate_workflow_webhook(
    workflow_id: int,
    node_id: str | None = None,
    node_type: str = "trigger_webhook",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    if node_type not in {"trigger_webhook", "trigger_event"}:
        raise ValidationError("Tipo de gatilho inválido para rotação de segredo.")
    return rotate_webhook_secret(
        db, workflow=workflow, node_id=node_id, node_type=node_type
    )


@router.get(
    "/{workflow_id}/versions", response_model=list[WorkflowVersionSummary]
)
def list_workflow_versions(
    workflow_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    rows = db.scalars(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow.id)
        .order_by(WorkflowVersion.version.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    if not rows and offset == 0:
        snapshot = snapshot_workflow_version(
            db,
            workflow,
            graph=workflow.graph,
            origin="baseline",
            created_by=current_user.id,
        )
        db.commit()
        db.refresh(snapshot)
        rows = [snapshot]
    return [WorkflowVersionSummary(**version_summary(row)) for row in rows]


@router.get(
    "/{workflow_id}/versions/{version}", response_model=WorkflowVersionDetail
)
def get_workflow_version(
    workflow_id: int,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    row = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.version == version,
        )
    )
    if row is None:
        raise NotFoundError("Versão do workflow não encontrada.")
    return WorkflowVersionDetail(
        **version_summary(row), graph=Graph(**(row.graph or {}))
    )


@router.post(
    "/{workflow_id}/versions/{version}/restore", response_model=WorkflowResponse
)
def restore_workflow_version(
    workflow_id: int,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    row = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.version == version,
        )
    )
    if row is None:
        raise NotFoundError("Versão do workflow não encontrada.")

    restored = normalize_graph(Graph(**(row.graph or {})), existing=workflow.graph)
    workflow.graph = restored
    workflow.version += 1
    db.commit()
    db.refresh(workflow)
    snapshot_workflow_version(
        db, workflow, origin="restore", created_by=current_user.id
    )
    db.commit()
    sync_schedules(db, workflow)
    return _response(workflow)


@router.get("/{workflow_id}/executions", response_model=list[ExecutionResponse])
def list_workflow_executions(
    workflow_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    rows = db.scalars(
        select(WorkflowExecution)
        .where(WorkflowExecution.workflow_id == workflow.id)
        .order_by(WorkflowExecution.created_at.desc())
        .limit(limit)
    ).all()
    return [
        ExecutionResponse.model_validate(row).model_copy(
            update={"workflow_name": workflow.name}
        )
        for row in rows
    ]


@router.get("/{workflow_id}/stats")
def workflow_stats(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = ensure_owned_workflow(db, current_user.id, workflow_id)
    rows = db.execute(
        select(WorkflowExecution.status, func.count(WorkflowExecution.id))
        .where(WorkflowExecution.workflow_id == workflow.id)
        .group_by(WorkflowExecution.status)
    ).all()
    by_status = {status: int(count) for status, count in rows}
    total = sum(by_status.values())
    finished = by_status.get("success", 0) + by_status.get("failed", 0)
    return {
        "workflow_id": workflow.id,
        "total": total,
        "by_status": by_status,
        "success_rate": round(by_status.get("success", 0) / finished * 100, 1) if finished else 0.0,
        "node_count": len((workflow.graph or {}).get("nodes", [])),
        "version": workflow.version,
        "node_types": sorted(
            {node.get("type") for node in (workflow.graph or {}).get("nodes", []) if node.get("type")}
        ),
        "registry_types": sorted(all_nodes().keys()),
    }
