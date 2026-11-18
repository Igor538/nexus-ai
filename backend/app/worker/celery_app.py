"""Celery application and beat schedule."""

from __future__ import annotations

from celery import Celery
from celery.schedules import schedule

from app.core.config import settings

celery_app = Celery(
    "nexus_ai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)

celery_app.conf.beat_schedule = {
    "scan-due-schedules": {
        "task": "app.worker.tasks.scan_schedules_task",
        "schedule": schedule(run_every=30.0),
    },
}
