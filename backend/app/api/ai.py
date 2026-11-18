"""AI provider catalog and usage reporting."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.services.ai.registry import available_providers
from app.services.ai.usage import usage_summary

router = APIRouter()


@router.get("/providers")
def list_providers(current_user: User = Depends(get_current_user)):
    return {
        "default_provider": settings.ai_default_provider,
        "default_model": settings.ai_default_model,
        "providers": available_providers(),
    }


@router.get("/usage")
def get_usage(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return usage_summary(db, current_user.id, days=days)
