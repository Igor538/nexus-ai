"""Scheduled workflow execution: finds due cron tasks and starts runs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.schedule import ScheduledTask
from app.models.workflow import Workflow
from app.services.executions import create_execution, has_active_execution

logger = logging.getLogger(__name__)


def run_due_schedules(limit: int = 20) -> int:
    db = SessionLocal()
    started = 0
    try:
        now = datetime.now(timezone.utc)
        query = (
            select(ScheduledTask)
            .where(
                ScheduledTask.is_active.is_(True),
                ScheduledTask.next_run_at.is_not(None),
                ScheduledTask.next_run_at <= now,
            )
            .order_by(ScheduledTask.next_run_at.asc())
            .limit(limit)
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)

        tasks = list(db.scalars(query).all())
        for task in tasks:
            workflow = db.get(Workflow, task.workflow_id)
            if workflow is None or not workflow.is_active:
                task.is_active = False
                db.commit()
                continue

            node_exists = any(
                node.get("id") == task.node_id and node.get("type") == "trigger_schedule"
                for node in (workflow.graph or {}).get("nodes", [])
            )
            if not node_exists:
                task.is_active = False
                db.commit()
                continue

            task.last_run_at = now
            task.next_run_at = _next_run(task.cron, task.timezone, now)
            db.commit()

            if has_active_execution(db, workflow.id):
                logger.info(
                    "schedule_skipped_active_execution",
                    extra={"workflow_id": workflow.id},
                )
                continue

            try:
                create_execution(
                    db,
                    workflow=workflow,
                    trigger="schedule",
                    trigger_data={
                        "node_id": task.node_id,
                        "scheduled_at": now.isoformat(),
                    },
                    input_data={"scheduled_at": now.isoformat()},
                )
                started += 1
            except Exception:
                logger.exception("schedule_dispatch_failed", extra={"workflow_id": workflow.id})
    finally:
        db.close()
    return started


def _next_run(cron: str, timezone_name: str, base: datetime) -> datetime:
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = timezone.utc
    local_base = base.astimezone(tz)
    if not croniter.is_valid(cron):
        return base
    return croniter(cron, local_base).get_next(datetime).astimezone(timezone.utc)
