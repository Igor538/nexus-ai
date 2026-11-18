"""Execution creation, dispatch, cancellation and statistics."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError
from app.models.ai_usage import AIUsage
from app.models.execution import WorkflowExecution
from app.models.workflow import Workflow
from app.services.executor.engine import ExecutionEngine

logger = logging.getLogger(__name__)


def dispatch_execution(execution_id: int) -> None:
    """Schedule an execution on the configured backend (Celery or inline thread)."""
    if settings.run_inline:
        thread = threading.Thread(
            target=_run_inline,
            args=(execution_id,),
            name=f"nexus-exec-{execution_id}",
            daemon=True,
        )
        thread.start()
        return

    from app.worker.celery_app import celery_app

    celery_app.send_task("app.worker.tasks.run_workflow_task", args=[execution_id])


def _run_inline(execution_id: int) -> None:
    try:
        asyncio.run(ExecutionEngine().run(execution_id))
    except Exception:  # pragma: no cover - defensive
        logger.exception("inline_execution_failed", extra={"execution_id": execution_id})


def has_active_execution(db: Session, workflow_id: int) -> bool:
    return (
        db.scalar(
            select(func.count(WorkflowExecution.id)).where(
                WorkflowExecution.workflow_id == workflow_id,
                WorkflowExecution.status.in_(["pending", "running"]),
            )
        )
        or 0
    ) > 0


def create_execution(
    db: Session,
    *,
    workflow: Workflow,
    trigger: str,
    trigger_data: dict[str, Any] | None = None,
    input_data: dict[str, Any] | None = None,
    dedupe_active: bool = False,
) -> WorkflowExecution:
    if dedupe_active and has_active_execution(db, workflow.id):
        raise ConflictError("Já existe uma execução em andamento para este workflow.")

    execution = WorkflowExecution(
        workflow_id=workflow.id,
        user_id=workflow.user_id,
        status="pending",
        trigger=trigger,
        trigger_data=trigger_data or {},
        input=input_data or {},
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    dispatch_execution(execution.id)
    return execution


def get_execution(db: Session, *, user_id: int, execution_id: int) -> WorkflowExecution:
    execution = db.scalar(
        select(WorkflowExecution).where(
            WorkflowExecution.id == execution_id, WorkflowExecution.user_id == user_id
        )
    )
    if execution is None:
        raise NotFoundError("Execução não encontrada.")
    return execution


def cancel_execution(db: Session, *, user_id: int, execution_id: int) -> WorkflowExecution:
    execution = get_execution(db, user_id=user_id, execution_id=execution_id)
    if execution.status in {"pending", "running"}:
        execution.status = "cancelled"
        execution.finished_at = datetime.now(timezone.utc)
        if execution.started_at:
            execution.duration_ms = int(
                (execution.finished_at - execution.started_at).total_seconds() * 1000
            )
        db.commit()
        db.refresh(execution)
    return execution


def retry_execution(db: Session, *, user_id: int, execution_id: int) -> WorkflowExecution:
    original = get_execution(db, user_id=user_id, execution_id=execution_id)
    workflow = db.scalar(
        select(Workflow).where(
            Workflow.id == original.workflow_id, Workflow.user_id == user_id
        )
    )
    if workflow is None:
        raise NotFoundError("Workflow não encontrado.")
    trigger_data = dict(original.trigger_data or {})
    trigger_data["retried_from"] = original.id
    execution = create_execution(
        db,
        workflow=workflow,
        trigger="retry",
        trigger_data=trigger_data,
        input_data=dict(original.input or {}),
        dedupe_active=True,
    )
    return execution


def list_executions(
    db: Session,
    *,
    user_id: int,
    workflow_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[WorkflowExecution], int]:
    conditions = [WorkflowExecution.user_id == user_id]
    if workflow_id:
        conditions.append(WorkflowExecution.workflow_id == workflow_id)
    if status:
        conditions.append(WorkflowExecution.status == status)

    total = db.scalar(select(func.count(WorkflowExecution.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(WorkflowExecution)
        .where(*conditions)
        .order_by(WorkflowExecution.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), int(total)


def workflow_names(db: Session, workflow_ids: set[int]) -> dict[int, str]:
    if not workflow_ids:
        return {}
    rows = db.execute(
        select(Workflow.id, Workflow.name).where(Workflow.id.in_(workflow_ids))
    ).all()
    return {row[0]: row[1] for row in rows}


def dashboard_stats(db: Session, *, user_id: int) -> dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=30)

    workflow_total = db.scalar(
        select(func.count(Workflow.id)).where(Workflow.user_id == user_id)
    ) or 0
    active_total = db.scalar(
        select(func.count(Workflow.id)).where(
            Workflow.user_id == user_id, Workflow.is_active.is_(True)
        )
    ) or 0

    status_rows = db.execute(
        select(WorkflowExecution.status, func.count(WorkflowExecution.id))
        .where(WorkflowExecution.user_id == user_id, WorkflowExecution.created_at >= since)
        .group_by(WorkflowExecution.status)
    ).all()
    by_status = {status: int(count) for status, count in status_rows}

    execution_total = sum(by_status.values())
    finished = by_status.get("success", 0) + by_status.get("failed", 0)
    success_rate = round((by_status.get("success", 0) / finished) * 100, 1) if finished else 0.0

    avg_duration = db.scalar(
        select(func.avg(WorkflowExecution.duration_ms)).where(
            WorkflowExecution.user_id == user_id,
            WorkflowExecution.created_at >= since,
            WorkflowExecution.duration_ms.is_not(None),
        )
    )

    daily_rows = db.execute(
        select(
            func.date(WorkflowExecution.created_at),
            WorkflowExecution.status,
            func.count(WorkflowExecution.id),
        )
        .where(WorkflowExecution.user_id == user_id, WorkflowExecution.created_at >= since)
        .group_by(func.date(WorkflowExecution.created_at), WorkflowExecution.status)
        .order_by(func.date(WorkflowExecution.created_at))
    ).all()
    daily: dict[str, dict[str, int]] = {}
    for day, status, count in daily_rows:
        key = str(day)
        daily.setdefault(key, {})
        daily[key][status] = int(count)

    ai_tokens = db.scalar(
        select(func.coalesce(func.sum(AIUsage.total_tokens), 0)).where(
            AIUsage.user_id == user_id, AIUsage.created_at >= since
        )
    ) or 0
    ai_cost = db.scalar(
        select(func.coalesce(func.sum(AIUsage.cost_usd), 0)).where(
            AIUsage.user_id == user_id, AIUsage.created_at >= since
        )
    ) or 0

    recent = db.scalars(
        select(WorkflowExecution)
        .where(WorkflowExecution.user_id == user_id)
        .order_by(WorkflowExecution.created_at.desc())
        .limit(8)
    ).all()
    names = workflow_names(db, {execution.workflow_id for execution in recent})

    return {
        "workflows": {"total": int(workflow_total), "active": int(active_total)},
        "executions": {
            "total": execution_total,
            "by_status": by_status,
            "success_rate": success_rate,
            "avg_duration_ms": int(avg_duration) if avg_duration else None,
        },
        "ai": {"tokens": int(ai_tokens), "cost_usd": float(ai_cost)},
        "daily": [
            {
                "date": day,
                "success": values.get("success", 0),
                "failed": values.get("failed", 0),
                "cancelled": values.get("cancelled", 0),
                "running": values.get("running", 0),
                "pending": values.get("pending", 0),
            }
            for day, values in sorted(daily.items())
        ],
        "recent_executions": [
            {
                "id": execution.id,
                "workflow_id": execution.workflow_id,
                "workflow_name": names.get(execution.workflow_id, "Workflow"),
                "status": execution.status,
                "trigger": execution.trigger,
                "duration_ms": execution.duration_ms,
                "created_at": execution.created_at,
            }
            for execution in recent
        ],
    }
