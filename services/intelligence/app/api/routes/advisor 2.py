from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.warehouse import MarketAdvisorRequest, MarketAdvisorRunResponse
from app.security import verify_internal_token
from app.services.market_advisor import generate_market_advisor_run

router = APIRouter(prefix="/advisor", tags=["advisor"], dependencies=[Depends(verify_internal_token)])


@router.post("/market", response_model=MarketAdvisorRunResponse)
async def market_advisor(payload: MarketAdvisorRequest, db: AsyncSession = Depends(get_db)):
    return await generate_market_advisor_run(db, payload)
