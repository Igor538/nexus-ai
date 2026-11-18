"""Liveness and readiness probes."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import engine

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
def health():
    return {
        "status": "ok",
        "service": "nexus-ai-api",
        "environment": settings.app_env,
        "version": "1.0.0",
    }


@router.get("/database")
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except SQLAlchemyError:
        logger.exception("database_health_failed")
        return {"status": "error", "database": "unavailable"}


@router.get("/redis")
def redis_health():
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception:
        return {"status": "error", "redis": "unavailable"}
