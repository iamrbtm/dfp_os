from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.security import verify_internal_token
from app.services.normalized_pipeline import get_pipeline_status, run_pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"], dependencies=[Depends(verify_internal_token)])


@router.post("/run")
async def pipeline_run(db: AsyncSession = Depends(get_db)):
    return await run_pipeline(db)


@router.get("/status")
async def pipeline_status(db: AsyncSession = Depends(get_db)):
    return await get_pipeline_status(db)
