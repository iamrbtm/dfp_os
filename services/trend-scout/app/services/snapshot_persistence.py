"""Snapshot + source-health persistence for the Trend Scout microservice.

Async wrappers around SQLAlchemy. Used by the pipeline orchestrator (Phase 4)
and by the integration tests (Phase 2).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SourceHealthRecord, TrendReport, TrendSnapshot

logger = logging.getLogger(__name__)


def _parse_scraped_at(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def persist_snapshots(
    session: AsyncSession,
    results: list[dict[str, Any]],
    business_id: int | None = None,
) -> int:
    """Insert TrendSnapshot rows for each result dict. Returns the count inserted."""
    now = datetime.now(timezone.utc)
    rows: list[TrendSnapshot] = []
    for snapshot in results:
        rows.append(
            TrendSnapshot(
                source=snapshot.get("source", "unknown"),
                keyword_or_category=snapshot.get("keyword_or_category", "unknown"),
                scraped_at=_parse_scraped_at(snapshot.get("scraped_at"), now),
                raw_metadata=snapshot,
                business_id=business_id,
                item_count=len(snapshot.get("items") or []),
            )
        )
    session.add_all(rows)
    await session.flush()
    logger.info("Persisted %d trend snapshots", len(rows))
    return len(rows)


async def persist_source_health(
    session: AsyncSession,
    source_health: list[dict[str, Any]],
    report_id: int | None = None,
    business_id: int | None = None,
) -> int:
    """Insert SourceHealthRecord rows. Returns count inserted."""
    rows: list[SourceHealthRecord] = []
    for entry in source_health:
        rows.append(
            SourceHealthRecord(
                report_id=report_id,
                source=entry.get("source", "unknown"),
                status=entry.get("status", "success"),
                keyword=entry.get("keyword"),
                item_count=entry.get("item_count", 0),
                error_message=entry.get("error_message"),
                throttled=False,
                throttle_reason=None,
                business_id=business_id,
                metadata_json=entry.get("metadata") or {},
            )
        )
    session.add_all(rows)
    await session.flush()
    return len(rows)


async def latest_source_health(session: AsyncSession, limit: int = 50) -> list[SourceHealthRecord]:
    stmt = select(SourceHealthRecord).order_by(SourceHealthRecord.scraped_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_empty_report(
    session: AsyncSession,
    business_id: int | None = None,
    run_id: str | None = None,
) -> TrendReport:
    """Create an empty TrendReport row reserved for a running pipeline."""
    report = TrendReport(
        business_id=business_id,
        run_id=run_id,
        summary="",
        top_opportunities=[],
        growing_categories=[],
        declining_categories=[],
    )
    session.add(report)
    await session.flush()
    return report
