from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import SourceHealthRecord
from app.schemas.api import SourceHealthListResponse
from app.schemas.api import SourceHealthRecord as SHRS
from app.security import SCOPE_READ, verify_internal_token

router = APIRouter(
    prefix="/source-health",
    tags=["source-health"],
    dependencies=[Depends(verify_internal_token)],
)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


def _to_record(row: SourceHealthRecord) -> SHRS:
    return SHRS(
        id=row.id,
        report_id=row.report_id,
        source=row.source,
        status=row.status,
        keyword=row.keyword,
        item_count=int(row.item_count or 0),
        error_message=row.error_message,
        throttled=bool(row.throttled),
        throttle_reason=row.throttle_reason,
        scraped_at=row.scraped_at or datetime.now(timezone.utc),
    )


@router.get("", response_model=SourceHealthListResponse)
async def list_source_health(
    source: str | None = Query(default=None, max_length=64),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_READ,
) -> SourceHealthListResponse:
    stmt = select(SourceHealthRecord)
    if source:
        stmt = stmt.where(SourceHealthRecord.source == source)
    if status_filter:
        stmt = stmt.where(SourceHealthRecord.status == status_filter)
    stmt = stmt.order_by(SourceHealthRecord.scraped_at.desc()).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    total_stmt = select(func.count(SourceHealthRecord.id))
    total = int((await session.execute(total_stmt)).scalar() or 0)
    return SourceHealthListResponse(
        items=[_to_record(r) for r in rows],
        total=total,
    )


@router.get("/latest")
async def latest_source_health(
    _token: str = SCOPE_READ,
) -> dict:
    """Return one row per source, the most recent."""
    async with async_session_factory() as session:
        from sqlalchemy import text

        stmt = text(
            "SELECT DISTINCT ON (source) source, status, keyword, item_count, "
            "error_message, throttled, throttle_reason, scraped_at "
            "FROM source_health_records ORDER BY source, scraped_at DESC"
        )
        result = await session.execute(stmt)
        return {
            "items": [
                {
                    "source": row.source,
                    "status": row.status,
                    "keyword": row.keyword,
                    "item_count": int(row.item_count or 0),
                    "error_message": row.error_message,
                    "throttled": bool(row.throttled),
                    "throttle_reason": row.throttle_reason,
                    "scraped_at": row.scraped_at.isoformat() if row.scraped_at else None,
                }
                for row in result.fetchall()
            ]
        }
