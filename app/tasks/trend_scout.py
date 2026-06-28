from __future__ import annotations

import logging

from flask import current_app

from app.celery_app import celery
from app.services.ai.trend_scout import run_full_pipeline

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
    logger.info("Trend Scout full pipeline starting...")
    api_key = current_app.config.get("OPENAI_API_KEY", "")
    model = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")

    result = run_full_pipeline(
        openai_api_key=api_key,
        openai_model=model,
    )

    if result.get("success"):
        logger.info(
            "Pipeline done: %d snapshots, report #%s, %d source errors",
            result["total_snapshots"],
            result.get("report_id"),
            len(result.get("failed_sources", [])),
        )
    else:
        logger.error("Pipeline failed: %s", result.get("error"))

    return result
