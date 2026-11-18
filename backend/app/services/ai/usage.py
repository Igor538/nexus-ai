"""AI usage accounting, quotas and cost reporting."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import RateLimitError
from app.models.ai_usage import AIUsage
from app.services.ai.registry import estimate_cost


def check_daily_quota(db: Session, user_id: int, reserved_tokens: int = 0) -> None:
    if settings.ai_daily_token_limit <= 0:
        return
    since = datetime.now(timezone.utc) - timedelta(days=1)
    used = db.scalar(
        select(func.coalesce(func.sum(AIUsage.total_tokens), 0)).where(
            AIUsage.user_id == user_id,
            AIUsage.created_at >= since,
        )
    ) or 0
    if int(used) + reserved_tokens > settings.ai_daily_token_limit:
        raise RateLimitError(
            "Limite diário de tokens de IA atingido. Tente novamente mais tarde ou aumente o limite."
        )


def record_usage(
    db: Session,
    *,
    user_id: int,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    workflow_id: int | None = None,
    execution_id: int | None = None,
    node_id: str | None = None,
    latency_ms: int | None = None,
) -> AIUsage:
    total = int(prompt_tokens) + int(completion_tokens)
    usage = AIUsage(
        user_id=user_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        node_id=node_id,
        provider=provider,
        model=model,
        prompt_tokens=int(prompt_tokens),
        completion_tokens=int(completion_tokens),
        total_tokens=total,
        cost_usd=Decimal(str(estimate_cost(model, prompt_tokens, completion_tokens))),
        latency_ms=latency_ms,
    )
    db.add(usage)
    db.commit()
    return usage


def usage_summary(db: Session, user_id: int, days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    totals = db.execute(
        select(
            func.coalesce(func.sum(AIUsage.prompt_tokens), 0),
            func.coalesce(func.sum(AIUsage.completion_tokens), 0),
            func.coalesce(func.sum(AIUsage.total_tokens), 0),
            func.coalesce(func.sum(AIUsage.cost_usd), 0),
            func.count(AIUsage.id),
        ).where(AIUsage.user_id == user_id, AIUsage.created_at >= since)
    ).one()

    by_model = db.execute(
        select(
            AIUsage.provider,
            AIUsage.model,
            func.sum(AIUsage.total_tokens),
            func.sum(AIUsage.cost_usd),
            func.count(AIUsage.id),
        )
        .where(AIUsage.user_id == user_id, AIUsage.created_at >= since)
        .group_by(AIUsage.provider, AIUsage.model)
        .order_by(func.sum(AIUsage.total_tokens).desc())
    ).all()

    return {
        "period_days": days,
        "prompt_tokens": int(totals[0] or 0),
        "completion_tokens": int(totals[1] or 0),
        "total_tokens": int(totals[2] or 0),
        "cost_usd": float(totals[3] or 0),
        "calls": int(totals[4] or 0),
        "daily_limit": settings.ai_daily_token_limit,
        "by_model": [
            {
                "provider": row[0],
                "model": row[1],
                "total_tokens": int(row[2] or 0),
                "cost_usd": float(row[3] or 0),
                "calls": int(row[4] or 0),
            }
            for row in by_model
        ],
    }
