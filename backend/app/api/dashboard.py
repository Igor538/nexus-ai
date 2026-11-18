"""Dashboard aggregates and schedule overview."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.executions import dashboard_stats
from app.services.workflow_service import upcoming_schedules

router = APIRouter()


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stats = dashboard_stats(db, user_id=current_user.id)
    stats["upcoming_schedules"] = upcoming_schedules(db, current_user.id)
    return stats
