from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import TrendReport
from app.schemas.api import ReportListResponse, ReportSummary
from app.security import SCOPE_READ, verify_internal_token

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(verify_internal_token)],
)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


def _to_summary(row: TrendReport) -> ReportSummary:
    pipeline_metadata = row.pipeline_metadata or {}
    return ReportSummary(
        id=row.id,
        report_date=row.report_date,
        summary=row.summary,
        top_opportunities=row.top_opportunities or [],
        growing_categories=row.growing_categories or [],
        declining_trends=row.declining_categories or [],
        scoring_version=row.scoring_version,
        business_id=row.business_id,
        run_id=row.run_id,
        pipeline_metadata=pipeline_metadata,
        pipeline_meta=pipeline_metadata,
        created_at=row.created_at,
    )


@router.get("", response_model=ReportListResponse)
async def list_reports(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_READ,
) -> ReportListResponse:
    stmt = select(TrendReport).order_by(TrendReport.report_date.desc()).offset(offset).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    total_stmt = select(func.count(TrendReport.id))
    total = int((await session.execute(total_stmt)).scalar() or 0)
    return ReportListResponse(
        items=[_to_summary(r) for r in rows],
        total=total,
    )


@router.get("/latest", response_model=ReportSummary)
async def latest_report(
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_READ,
) -> ReportSummary:
    stmt = select(TrendReport).order_by(TrendReport.report_date.desc()).limit(1)
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_reports", "message": "No reports available."},
        )
    return _to_summary(row)


@router.get("/{report_id}", response_model=ReportSummary)
async def get_report(
    report_id: int,
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_READ,
) -> ReportSummary:
    row = await session.get(TrendReport, report_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "report_not_found", "message": f"No report id={report_id}."},
        )
    return _to_summary(row)
