"""Celery tasks for the Trend Scout microservice.

Two tasks:
- ``trend_scout_pipeline`` runs the full pipeline (fetchers + analyzer).
- ``calibrate_trend_scout`` runs the backtest + calibration.

Both run on the low-priority ``trend_scout`` queue. They are not CPU-heavy
but can take a few minutes (15-minute soft time limit), so they must not
preempt the main app's high-priority tasks.

The tasks use async session factories (the microservice is async) via a
Celery-friendly ``asyncio.run`` bridge. This keeps the code self-contained
without requiring a fully async Celery worker.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery
from app.config import settings
from app.database import async_session_factory
from app.services.calibration import run_calibration
from app.services.pipeline_runner import run_full_pipeline

logger = logging.getLogger(__name__)


def _session_factory_coro():
    """Acquire a session from the async factory for use in asyncio.run."""

    async def _factory() -> AsyncSession:
        session = async_session_factory()
        return session

    return _factory()


@celery.task(
    bind=True,
    name="app.workers.tasks.trend_scout_pipeline",
    max_retries=1,
    default_retry_delay=300,
    soft_time_limit=settings.pipeline_soft_time_limit_seconds,
    time_limit=settings.pipeline_hard_time_limit_seconds,
    acks_late=True,
)
def trend_scout_pipeline(self, *, run_id: str | None = None, trigger: str = "scheduled") -> dict[str, Any]:
    """Run the full Trend Scout pipeline. Returns the run summary dict."""
    task_id = self.request.id or "unknown"
    run_id = run_id or f"celery-{task_id}"
    logger.info("[Task %s] Trend Scout pipeline starting", task_id)

    async def _factory() -> AsyncSession:
        return async_session_factory()

    summary = asyncio.run(
        run_full_pipeline(
            session_factory=_factory,
            run_id=run_id,
            trigger=trigger,
            progress_callback=lambda completed, total, step, status: self.update_state(
                state="PROGRESS",
                meta={"step": step, "status": status, "completed": completed, "total": total},
            ),
        )
    )
    logger.info("[Task %s] pipeline finished: success=%s", task_id, summary.get("success"))
    return summary


@celery.task(
    bind=True,
    name="app.workers.tasks.calibrate_trend_scout",
    max_retries=1,
    default_retry_delay=300,
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
)
def calibrate_trend_scout(self, *, trigger: str = "manual", lookback_reports: int = 12) -> dict[str, Any]:
    """Run calibration (backtest + tuning hints) and persist the record."""
    task_id = self.request.id or "unknown"
    logger.info("[Task %s] Trend Scout calibration starting", task_id)

    async def _run() -> dict[str, Any]:
        async with async_session_factory() as session:
            record = await run_calibration(
                session,
                trigger=trigger,
                lookback_reports=lookback_reports,
            )
            return record

    record = asyncio.run(_run())
    logger.info("[Task %s] calibration finished: status=%s", task_id, record.get("status"))
    return record
