from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import TrendOpportunityScore
from app.schemas.api import (
    OpportunityActionRequest,
    OpportunityListResponse,
    OpportunityScore,
)
from app.security import SCOPE_READ, SCOPE_WRITE, verify_internal_token

router = APIRouter(
    prefix="/opportunities",
    tags=["opportunities"],
    dependencies=[Depends(verify_internal_token)],
)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


def _to_score(row: TrendOpportunityScore) -> OpportunityScore:
    breakdown = row.score_breakdown or {}

    def _num(key: str, fallback: float = 0.0) -> float:
        value = breakdown.get(key, fallback)
        try:
            return float(value)
        except TypeError, ValueError:
            return fallback

    def _int(key: str, fallback: int = 0) -> int:
        return int(round(_num(key, fallback)))

    risk_raw = breakdown.get("license_risk_score") or breakdown.get("license_risk") or row.license_risk
    if isinstance(risk_raw, str):
        risk_score = {"low": 20, "medium": 50, "high": 80, "unknown": 50}.get(risk_raw.lower(), 50)
        license_status = risk_raw
    else:
        risk_score = int(round(float(risk_raw or 0)))
        license_status = breakdown.get("license_status")

    score = int(round(float(row.score)))
    velocity = int(round(float(row.velocity)))
    sources = breakdown.get("sources") or [row.source]
    if isinstance(sources, str):
        sources = [sources]

    return OpportunityScore(
        id=row.id,
        report_id=row.report_id,
        keyword=row.keyword,
        source=row.source,
        score=float(row.score),
        title=breakdown.get("title") or row.keyword,
        candidate_type=breakdown.get("candidate_type") or "potential",
        product_id=breakdown.get("product_id"),
        opportunity_score=score,
        action=row.recommended_action,
        rank=breakdown.get("rank"),
        recommended_action=row.recommended_action,
        velocity=float(row.velocity),
        trend_velocity=velocity,
        momentum=float(row.momentum),
        purchase_intent=int(round(float(row.purchase_intent))),
        price_resilience=_int("price_resilience"),
        low_saturation=_int("low_saturation"),
        local_fit=int(round(float(row.local_relevance))),
        production_fit=_int("production_fit"),
        license_risk=risk_score,
        license_status=license_status,
        local_relevance=float(row.local_relevance),
        inventory_available=breakdown.get("inventory_available"),
        base_price=breakdown.get("base_price"),
        sources=sources,
        match_confidence=breakdown.get("match_confidence"),
        dismissed=bool(row.dismissed),
        score_breakdown=breakdown,
    )


@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    report_id: int | None = Query(default=None, ge=1),
    source: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=64),
    include_dismissed: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_READ,
) -> OpportunityListResponse:
    stmt = select(TrendOpportunityScore)
    if report_id is not None:
        stmt = stmt.where(TrendOpportunityScore.report_id == report_id)
    if source:
        stmt = stmt.where(TrendOpportunityScore.source == source)
    if action:
        stmt = stmt.where(TrendOpportunityScore.recommended_action == action)
    if not include_dismissed:
        stmt = stmt.where(TrendOpportunityScore.dismissed.is_(False))
    stmt = stmt.order_by(TrendOpportunityScore.score.desc()).offset(offset).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())

    count_stmt = select(func.count(TrendOpportunityScore.id))
    if report_id is not None:
        count_stmt = count_stmt.where(TrendOpportunityScore.report_id == report_id)
    if source:
        count_stmt = count_stmt.where(TrendOpportunityScore.source == source)
    if action:
        count_stmt = count_stmt.where(TrendOpportunityScore.recommended_action == action)
    if not include_dismissed:
        count_stmt = count_stmt.where(TrendOpportunityScore.dismissed.is_(False))
    total = int((await session.execute(count_stmt)).scalar() or 0)
    return OpportunityListResponse(
        items=[_to_score(r) for r in rows],
        total=total,
    )


@router.get("/{score_id}", response_model=OpportunityScore)
async def get_opportunity(
    score_id: int,
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_READ,
) -> OpportunityScore:
    row = await session.get(TrendOpportunityScore, score_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "opportunity_not_found", "message": f"No opportunity id={score_id}."},
        )
    return _to_score(row)


@router.post("/{score_id}/dismiss", response_model=OpportunityScore)
async def dismiss_opportunity(
    score_id: int,
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_WRITE,
) -> OpportunityScore:
    row = await session.get(TrendOpportunityScore, score_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "opportunity_not_found", "message": f"No opportunity id={score_id}."},
        )
    row.dismissed = True
    await session.commit()
    await session.refresh(row)
    return _to_score(row)


@router.post("/{score_id}/undismiss", response_model=OpportunityScore)
async def undismiss_opportunity(
    score_id: int,
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_WRITE,
) -> OpportunityScore:
    row = await session.get(TrendOpportunityScore, score_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "opportunity_not_found", "message": f"No opportunity id={score_id}."},
        )
    row.dismissed = False
    await session.commit()
    await session.refresh(row)
    return _to_score(row)


@router.post("/{score_id}/action", response_model=OpportunityScore)
async def action_opportunity(
    score_id: int,
    request: OpportunityActionRequest,
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_WRITE,
) -> OpportunityScore:
    row = await session.get(TrendOpportunityScore, score_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "opportunity_not_found", "message": f"No opportunity id={score_id}."},
        )
    allowed = {"print_now", "watch", "skip", "dismiss"}
    if request.action not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_action",
                "message": f"action must be one of {sorted(allowed)}",
            },
        )
    row.recommended_action = request.action
    if request.action == "dismiss":
        row.dismissed = True
    await session.commit()
    await session.refresh(row)
    return _to_score(row)
