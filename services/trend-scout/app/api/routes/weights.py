from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models import TrendWeight
from app.schemas.api import WeightEntry, WeightListResponse, WeightSaveRequest
from app.security import SCOPE_READ, SCOPE_WRITE, verify_internal_token
from app.services import weights as weights_service

router = APIRouter(
    prefix="/weights",
    tags=["weights"],
    dependencies=[Depends(verify_internal_token)],
)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


def _to_entry(row: TrendWeight) -> WeightEntry:
    return WeightEntry(
        group=row.group or "default",
        key=row.key,
        value=float(row.value),
        description=row.description,
    )


@router.get("", response_model=WeightListResponse)
async def list_weights(
    group: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=200, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_READ,
) -> WeightListResponse:
    stmt = select(TrendWeight).limit(limit)
    if group:
        stmt = stmt.where(TrendWeight.group == group)
    rows = list((await session.execute(stmt)).scalars().all())
    total_stmt = select(func.count(TrendWeight.id))
    total = int((await session.execute(total_stmt)).scalar() or 0)
    return WeightListResponse(
        items=[_to_entry(r) for r in rows],
        total=total,
    )


@router.get("/defaults")
async def default_weights(_token: str = SCOPE_READ) -> dict[str, Any]:
    return {
        "score": weights_service.DEFAULT_SCORE_WEIGHTS,
        "source": weights_service.DEFAULT_SOURCE_WEIGHTS,
        "buyer": weights_service.DEFAULT_BUYER_SOURCE_WEIGHTS,
        "metric": weights_service.DEFAULT_METRIC_WEIGHTS,
        "source_enabled": {k: True for k in weights_service.DEFAULT_SOURCE_WEIGHTS},
    }


@router.post("/save", response_model=WeightListResponse)
async def save_weights(
    payload: WeightSaveRequest,
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_WRITE,
) -> WeightListResponse:
    if not payload.entries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "empty_entries", "message": "No weight entries provided."},
        )
    for entry in payload.entries:
        await weights_service.save_weight(
            session,
            group=entry.group,
            key=entry.key,
            value=entry.value,
            description=entry.description,
        )
    await session.commit()

    rows = list((await session.execute(select(TrendWeight))).scalars().all())
    return WeightListResponse(
        items=[_to_entry(r) for r in rows],
        total=len(rows),
    )


@router.post("/seed-defaults", response_model=WeightListResponse)
async def seed_defaults(
    session: AsyncSession = Depends(get_session),
    _token: str = SCOPE_WRITE,
) -> WeightListResponse:
    await weights_service.seed_default_weights(session)
    await session.commit()
    rows = list((await session.execute(select(TrendWeight))).scalars().all())
    return WeightListResponse(
        items=[_to_entry(r) for r in rows],
        total=len(rows),
    )
