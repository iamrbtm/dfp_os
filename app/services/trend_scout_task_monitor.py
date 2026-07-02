from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models import TrendTaskRun

logger = logging.getLogger(__name__)

VALID_TRIGGERS = ("manual", "cli", "api", "scheduled")
VALID_STATUSES = ("pending", "running", "completed", "failed", "cancelled")


def create_task_run(
    task_id: str,
    trigger: str = "manual",
    total_steps: int = 0,
    celery_task_id: str | None = None,
) -> TrendTaskRun:
    trigger = trigger if trigger in VALID_TRIGGERS else "manual"
    run = TrendTaskRun(
        task_id=task_id,
        celery_task_id=celery_task_id,
        trigger=trigger,
        status="pending",
        total_steps=total_steps,
    )
    db.session.add(run)
    db.session.commit()
    return run


def start_task_run(task_id: str) -> TrendTaskRun | None:
    run = db.session.query(TrendTaskRun).filter_by(task_id=task_id).first()
    if not run:
        return None
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    db.session.commit()
    return run


def update_task_progress(
    task_id: str,
    completed_steps: int,
    total_steps: int,
    current_step: str,
    status: str = "running",
) -> TrendTaskRun | None:
    run = db.session.query(TrendTaskRun).filter_by(task_id=task_id).first()
    if not run:
        return None
    run.completed_steps = completed_steps
    run.total_steps = total_steps
    run.current_step = current_step
    run.status = status
    db.session.commit()
    return run


def complete_task_run(
    task_id: str,
    report_id: int | None = None,
    source_health: list[dict] | None = None,
    result_meta: dict | None = None,
    error_message: str | None = None,
) -> TrendTaskRun | None:
    run = db.session.query(TrendTaskRun).filter_by(task_id=task_id).first()
    if not run:
        return None
    run.status = "failed" if error_message else "completed"
    run.completed_at = datetime.now(timezone.utc)
    if run.started_at:
        run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
    run.error_message = error_message
    run.report_id = report_id
    run.source_health_summary = source_health
    run.result_meta = result_meta
    db.session.commit()
    return run


def cancel_task_run(task_id: str) -> TrendTaskRun | None:
    run = db.session.query(TrendTaskRun).filter_by(task_id=task_id).first()
    if not run:
        return None
    run.status = "cancelled"
    run.completed_at = datetime.now(timezone.utc)
    if run.started_at:
        run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
    db.session.commit()
    return run


def get_recent_task_runs(limit: int = 50) -> list[TrendTaskRun]:
    return (
        db.session.query(TrendTaskRun)
        .order_by(TrendTaskRun.created_at.desc())
        .limit(limit)
        .all()
    )


def get_task_run(task_id: str) -> TrendTaskRun | None:
    return db.session.query(TrendTaskRun).filter_by(task_id=task_id).first()
