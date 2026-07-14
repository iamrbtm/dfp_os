from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DecisionOutcome
from app.schemas.knowledge import DecisionOutcomeCreate


async def record_decision_outcome(db: AsyncSession, payload: DecisionOutcomeCreate) -> DecisionOutcome:
    outcome = DecisionOutcome(**payload.model_dump())
    db.add(outcome)
    await db.commit()
    await db.refresh(outcome)
    return outcome


async def list_decision_outcomes(db: AsyncSession, limit: int = 50) -> list[DecisionOutcome]:
    result = await db.execute(select(DecisionOutcome).order_by(DecisionOutcome.created_at.desc()).limit(limit))
    return list(result.scalars().all())
