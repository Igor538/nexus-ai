"""Execution history, details, cancellation and retry."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.execution import ExecutionLog
from app.models.user import User
from app.schemas.execution import (
    ExecutionDetailResponse,
    ExecutionLogResponse,
    ExecutionResponse,
)
from app.services.executions import (
    cancel_execution,
    get_execution,
    list_executions,
    retry_execution,
    workflow_names,
)

router = APIRouter()


@router.get("", response_model=dict)
def get_executions(
    workflow_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows, total = list_executions(
        db,
        user_id=current_user.id,
        workflow_id=workflow_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    names = workflow_names(db, {row.workflow_id for row in rows})
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            ExecutionResponse.model_validate(row)
            .model_copy(update={"workflow_name": names.get(row.workflow_id)})
            .model_dump(mode="json")
            for row in rows
        ],
    }


@router.get("/{execution_id}", response_model=ExecutionDetailResponse)
def get_execution_detail(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    execution = get_execution(db, user_id=current_user.id, execution_id=execution_id)
    logs = db.scalars(
        select(ExecutionLog)
        .where(ExecutionLog.execution_id == execution.id)
        .order_by(ExecutionLog.id.asc())
    ).all()
    names = workflow_names(db, {execution.workflow_id})
    return ExecutionDetailResponse.model_validate(execution).model_copy(
        update={
            "workflow_name": names.get(execution.workflow_id),
            "logs": [ExecutionLogResponse.model_validate(log) for log in logs],
        }
    )


@router.post("/{execution_id}/cancel", response_model=ExecutionResponse)
def cancel(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    execution = cancel_execution(db, user_id=current_user.id, execution_id=execution_id)
    names = workflow_names(db, {execution.workflow_id})
    return ExecutionResponse.model_validate(execution).model_copy(
        update={"workflow_name": names.get(execution.workflow_id)}
    )


@router.post(
    "/{execution_id}/retry",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    execution = retry_execution(db, user_id=current_user.id, execution_id=execution_id)
    names = workflow_names(db, {execution.workflow_id})
    return ExecutionResponse.model_validate(execution).model_copy(
        update={"workflow_name": names.get(execution.workflow_id)}
    )
