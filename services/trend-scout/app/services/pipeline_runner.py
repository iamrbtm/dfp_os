"""Top-level pipeline runner.

Composes fetchers, snapshot persistence, analyzer, AI synthesis, and source
health persistence. Used by both:
- The Celery task (app/workers/tasks.py) — runs in a Celery worker context
- The Flask proxy (Phase 6) — runs in a request context

The runner is async and accepts an optional ``progress_callback`` for HTMX
polling (the legacy behavior in the monolith is preserved).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analysis.orchestrator import run_analysis
from app.services.fetcher_pipeline import run_all_sources
from app.services.snapshot_persistence import (
    create_empty_report,
    persist_snapshots,
    persist_source_health,
)
from app.services.weights import seed_default_weights
from app.workers.task_monitor import (
    complete_task_run,
    create_task_run,
    get_task_run,
    start_task_run,
    update_task_progress,
)

logger = logging.getLogger(__name__)


ProgressCallback = Callable[[int, int, str, str], None]


async def run_full_pipeline(
    session_factory: Callable[[], Awaitable[AsyncSession]],
    run_id: str | None = None,
    task_id: str | None = None,
    trigger: str = "scheduled",
    business_id: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run the full pipeline and return a summary dict.

    ``session_factory`` is awaited once to acquire a session because Celery
    worker boot may not have an active session.
    """
    run_id = run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S")
    started_at = datetime.now(timezone.utc).isoformat()

    monitor_task_id = task_id or f"pipeline-{run_id}"
    if not get_task_run(monitor_task_id):
        create_task_run(
            task_id=monitor_task_id,
            trigger=trigger,
            total_steps=12,
            run_id=run_id,
        )
    start_task_run(monitor_task_id)

    completed_steps = 0

    async def _step(step: str, status: str = "completed") -> None:
        nonlocal completed_steps
        completed_steps = min(completed_steps + 1, 12)
        update_task_progress(
            task_id=monitor_task_id,
            completed_steps=completed_steps,
            current_step=step,
            status=status,
        )
        if progress_callback is not None:
            progress_callback(0, 12, step, status)

    try:
        await _step("initializing")
        session = await session_factory()

        try:
            await _step("seeding_weights")
            await seed_default_weights(session)
            await session.commit()

            await _step("fetching_sources")
            scraped = run_all_sources()

            await _step("persisting_snapshots")
            snapshot_count = await persist_snapshots(session, scraped, business_id=business_id)
            await session.commit()

            from app.services.fetcher_pipeline import aggregate_source_health

            source_health = aggregate_source_health(scraped)

            await _step("creating_report")
            report = await create_empty_report(session, business_id=business_id, run_id=run_id)
            await session.commit()

            await _step("analyzing")
            await run_analysis(session, business_id=business_id, source_health=source_health)

            await _step("persisting_source_health")
            await persist_source_health(session, source_health, report_id=report.id)
            await session.commit()
        finally:
            await session.close()

        await _step("complete", status="completed")
        complete_task_run(monitor_task_id, status="success")

        return {
            "run_id": run_id,
            "started_at": started_at,
            "success": True,
            "snapshots_inserted": snapshot_count,
            "report_id": report.id,
            "source_health": source_health,
        }
    except Exception as exc:
        logger.exception("Pipeline run %s failed", run_id)
        complete_task_run(monitor_task_id, status="failed", error=str(exc))
        await _step("failed", status="failed")
        return {
            "run_id": run_id,
            "started_at": started_at,
            "success": False,
            "error": str(exc),
        }
