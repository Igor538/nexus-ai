"""Celery tasks for execution and scheduling."""

from __future__ import annotations

import asyncio
import logging

from app.core.logging import configure_logging
from app.services.executor.engine import ExecutionEngine
from app.services.scheduling import run_due_schedules
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.run_workflow_task", bind=True, max_retries=1)
def run_workflow_task(self, execution_id: int) -> dict:
    configure_logging()
    try:
        asyncio.run(ExecutionEngine().run(execution_id))
        return {"execution_id": execution_id, "status": "finished"}
    except Exception as exc:  # pragma: no cover - worker defensive path
        logger.exception("worker_execution_failed", extra={"execution_id": execution_id})
        raise self.retry(exc=exc, countdown=5) if self.request.retries < 1 else exc


@celery_app.task(name="app.worker.tasks.scan_schedules_task")
def scan_schedules_task() -> dict:
    configure_logging()
    started = run_due_schedules()
    return {"started": started}
