from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.celery_app import celery
from app.extensions import db
from app.models.trend import TrendSnapshot
from app.services.ai.trend_scout import run_all_sources

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
    logger.info("Trend Scout pipeline starting...")
    now = datetime.now(timezone.utc)
    total_inserted = 0
    failed_sources: list[str] = []

    try:
        snapshots = run_all_sources()
    except Exception as exc:
        logger.error("Pipeline crashed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "total_inserted": 0,
            "failed_sources": ["pipeline"],
        }

    for snapshot in snapshots:
        source = snapshot.get("source", "unknown")
        keyword = snapshot.get("keyword_or_category", "unknown")
        errors = snapshot.get("errors", [])

        if errors:
            failed_sources.append(f"{source}/{keyword}: {'; '.join(errors)}")
            logger.warning("Source %s/%s had errors: %s", source, keyword, errors)

        record = TrendSnapshot(
            source=source,
            keyword_or_category=keyword,
            scraped_at=now,
            raw_metadata=snapshot,
        )
        db.session.add(record)
        total_inserted += 1

    try:
        db.session.commit()
        logger.info(
            "Trend Scout pipeline done: %d snapshots inserted, %d sources with errors",
            total_inserted,
            len(failed_sources),
        )
        return {
            "success": True,
            "total_inserted": total_inserted,
            "failed_sources": failed_sources,
        }
    except Exception as exc:
        db.session.rollback()
        logger.error("DB commit failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "total_inserted": total_inserted,
            "failed_sources": failed_sources,
        }
