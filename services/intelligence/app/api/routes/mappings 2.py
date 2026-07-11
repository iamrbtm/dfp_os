from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import HistoricalAliasMapping, utcnow
from app.schemas.mappings import AliasMappingCreate, AliasMappingListResponse, AliasMappingResponse, AliasMappingReview
from app.security import verify_internal_token
from app.services.mapping import create_alias_mapping, list_alias_mappings

router = APIRouter(prefix="/mappings", tags=["mappings"], dependencies=[Depends(verify_internal_token)])


@router.get("", response_model=AliasMappingListResponse)
async def list_mappings(
    source: str | None = None,
    entity_type: str | None = None,
    reviewed: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    return AliasMappingListResponse(items=await list_alias_mappings(db, source, entity_type, reviewed))


@router.post("", response_model=AliasMappingResponse, status_code=status.HTTP_201_CREATED)
async def create_mapping(payload: AliasMappingCreate, db: AsyncSession = Depends(get_db)):
    return await create_alias_mapping(db, payload)


@router.post("/{mapping_id}/review", response_model=AliasMappingResponse)
async def review_mapping(mapping_id: str, payload: AliasMappingReview, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HistoricalAliasMapping).where(HistoricalAliasMapping.id == mapping_id))
    mapping = result.scalar_one_or_none()
    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "mapping_not_found", "message": "Historical alias mapping was not found."},
        )
    mapping.target_entity_type = payload.target_entity_type
    mapping.target_entity_id = payload.target_entity_id
    mapping.target_display_name = payload.target_display_name
    mapping.match_confidence = payload.match_confidence
    mapping.reviewed = True
    mapping.reviewed_by = payload.reviewed_by
    mapping.reviewed_at = utcnow()
    mapping.notes = payload.notes
    await db.commit()
    await db.refresh(mapping)
    return mapping
