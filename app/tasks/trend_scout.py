from __future__ import annotations

import logging

from flask import current_app

from app.celery_app import celery
from app.services.ai.trend_scout import FETCHERS, run_full_pipeline

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    max_retries=1,
    default_retry_delay=300,
    soft_time_limit=900,
    time_limit=960,
    acks_late=True,
)
def trend_scout_pipeline(self) -> dict:
    task_id = self.request.id
    logger.info("[Task %s] Trend Scout full pipeline starting...", task_id)

    api_key = current_app.config.get("OPENAI_API_KEY", "")
    model = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")

    total_steps = len(FETCHERS) + 1  # fetch sources + analysis

    def _on_progress(completed, total, step_name, status):
        meta = {
            "current": completed,
            "total": total,
            "step": step_name,
            "status": status,
        }
        self.update_state(state="PROGRESS", meta=meta)
        if status == "failed":
            logger.warning("[Task %s] Step %d/%d failed: %s", task_id, completed, total, step_name)
        elif status == "completed":
            logger.info("[Task %s] Step %d/%d completed: %s", task_id, completed, total, step_name)

    self.update_state(
        state="PROGRESS",
        meta={"current": 0, "total": total_steps, "step": "initializing", "status": "running"},
    )

    result = run_full_pipeline(
        openai_api_key=api_key,
        openai_model=model,
        progress_callback=_on_progress,
    )

    if result.get("success"):
        logger.info(
            "[Task %s] Pipeline done: %d snapshots, report #%s, %d source errors",
            task_id,
            result["total_snapshots"],
            result.get("report_id"),
            len(result.get("failed_sources", [])),
        )
    else:
        logger.error("[Task %s] Pipeline failed: %s", task_id, result.get("error"))

    return result
