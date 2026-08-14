"""Dispatch tasks for the main Flask app.

The Celery beat schedule still lives in ``app/celery_app.py``. These tasks
are short — they POST to the trend-scout microservice to enqueue a run, and
then return. The heavy lifting happens in the microservice's own Celery
queue (``trend_scout``, low priority) so it cannot starve the main app.

Wire-up path:
- ``app.celery_app.py`` beat schedule triggers ``app.tasks.dispatch_trend_scout.dispatch_trend_scout_run``
- This task POSTs to ``{TREND_SCOUT_SERVICE_URL}/api/v1/pipeline/run`` (Phase 5)
- The microservice enqueues onto its own ``trend_scout`` Celery queue
- The microservice's worker consumes and runs the pipeline
"""

from __future__ import annotations

import logging

import httpx
from flask import current_app

from app.celery_app import celery

logger = logging.getLogger(__name__)


def _internal_token() -> str:
    try:
        return current_app.config.get("TREND_SCOUT_INTERNAL_API_TOKEN", "")
    except RuntimeError:
        return ""


def _service_url() -> str:
    try:
        return current_app.config.get("TREND_SCOUT_SERVICE_URL", "http://trend-scout:8093")
    except RuntimeError:
        return "http://trend-scout:8093"


def _post(path: str, payload: dict, timeout: float = 10.0) -> dict:
    token = _internal_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = httpx.post(
        f"{_service_url()}{path}",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json() if response.content else {}


@celery.task(
    bind=True,
    name="app.tasks.dispatch_trend_scout.dispatch_trend_scout_run",
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
)
def dispatch_trend_scout_run(self, *, trigger: str = "scheduled") -> dict:
    """Beat fires this on Monday 06:00 (cron). It POSTs to the microservice."""
    try:
        return _post(
            "/api/v1/pipeline/run",
            {"trigger": trigger, "run_id": f"beat-{trigger}"},
        )
    except httpx.HTTPError as exc:
        logger.warning("trend-scout dispatch failed: %s; retrying", exc)
        raise self.retry(exc=exc) from exc


@celery.task(
    bind=True,
    name="app.tasks.dispatch_trend_scout.dispatch_trend_scout_calibration",
    max_retries=2,
    default_retry_delay=300,
    acks_late=True,
)
def dispatch_trend_scout_calibration(
    self, *, trigger: str = "monthly", lookback_reports: int = 12
) -> dict:
    """Beat fires this on the 1st of each month at 05:00 (cron)."""
    try:
        return _post(
            "/api/v1/calibration/run",
            {
                "trigger": trigger,
                "lookback_reports": lookback_reports,
            },
        )
    except httpx.HTTPError as exc:
        logger.warning("trend-scout calibration dispatch failed: %s; retrying", exc)
        raise self.retry(exc=exc) from exc
