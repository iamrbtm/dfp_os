from __future__ import annotations

import logging
import uuid

from flask import current_app

from app.celery_app import celery
from app.extensions import db
from app.services.ai.trend_scout import FETCHERS, run_full_pipeline
from app.services.trend_scout_task_monitor import (
    complete_task_run,
    create_task_run,
    start_task_run,
    update_task_progress,
)

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
    model = current_app.config.get(
        "OPENAI_MODEL_TREND_SCOUT",
        current_app.config.get(
            "OPENAI_MODEL_ANALYTICS", current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
        ),
    )

    total_steps = len(FETCHERS) + 1
    internal_task_id = f"celery-{task_id}"

    try:
        create_task_run(
            task_id=internal_task_id,
            trigger="scheduled",
            total_steps=total_steps,
            celery_task_id=task_id,
        )
        start_task_run(internal_task_id)
    except Exception as exc:
        logger.warning("[Task %s] TaskRun creation failed: %s", task_id, exc)

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
        try:
            update_task_progress(
                task_id=internal_task_id,
                completed_steps=completed,
                total_steps=total,
                current_step=step_name,
                status="running" if status != "failed" else "running",
            )
        except Exception:
            pass

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
        try:
            complete_task_run(
                task_id=internal_task_id,
                report_id=result.get("report_id"),
                source_health=result.get("source_health"),
                result_meta={
                    "total_snapshots": result.get("total_snapshots", 0),
                    "successful_sources": len(result.get("successful_sources", [])),
                    "failed_sources": len(result.get("failed_sources", [])),
                },
            )
        except Exception as exc:
            logger.warning("[Task %s] TaskRun completion failed: %s", task_id, exc)

        try:
            from app.services.trend_scout_prune import prune_old_data
            db.session.commit()
            prune_result = prune_old_data(dry_run=False)
            if prune_result.get("status") == "pruned":
                logger.info(
                    "[Task %s] Auto-prune: removed %d old reports, %d snapshots",
                    task_id,
                    prune_result["pruned_reports"],
                    prune_result["pruned_snapshots"],
                )
        except Exception as exc:
            logger.warning("[Task %s] Auto-prune failed: %s", task_id, exc)
    else:
        logger.error("[Task %s] Pipeline failed: %s", task_id, result.get("error"))
        try:
            complete_task_run(
                task_id=internal_task_id,
                error_message=result.get("error", "Unknown error"),
                result_meta={"total_snapshots": result.get("total_snapshots", 0)},
            )
        except Exception as exc:
            logger.warning("[Task %s] TaskRun failure recording failed: %s", task_id, exc)

    return result
