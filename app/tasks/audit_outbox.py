"""Celery task that drains the Redis audit outbox into the microservice.

Scheduled by ``app.celery_app.make_celery``'s beat every
``AUDIT_OUTBOX_FLUSH_INTERVAL_SECONDS`` (default 30s). Also dispatched
once at app startup so any events buffered while the worker was down
are replayed as soon as possible.
"""

from __future__ import annotations

import logging

from app.celery_app import celery
from app.services.audit_client import get_audit_client

logger = logging.getLogger(__name__)


@celery.task(name="app.tasks.audit_outbox.flush_outbox")
def flush_audit_outbox() -> dict[str, int]:
    """Replay queued audit events into the microservice."""
    from app import create_app

    app = create_app()
    with app.app_context():
        client = get_audit_client()
        result = client.flush_outbox()
        if result.get("remaining", 0):
            logger.info(
                "audit outbox flush: drained=%d remaining=%d",
                result.get("drained", 0),
                result.get("remaining", 0),
            )
        return result
