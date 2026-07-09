from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HistoricalAliasMapping, utcnow
from app.schemas.mappings import AliasMappingCreate


def normalize_source_value(value: str) -> str:
    return " ".join(value.strip().casefold().split())


async def create_alias_mapping(db: AsyncSession, payload: AliasMappingCreate) -> HistoricalAliasMapping:
    mapping = HistoricalAliasMapping(
        source=payload.source,
        entity_type=payload.entity_type,
        source_value=payload.source_value,
        normalized_value=payload.normalized_value or normalize_source_value(payload.source_value),
        target_entity_type=payload.target_entity_type,
        target_entity_id=payload.target_entity_id,
        target_display_name=payload.target_display_name,
        match_confidence=Decimal(payload.match_confidence),
        reviewed=payload.reviewed,
        reviewed_by=payload.reviewed_by if payload.reviewed else None,
        reviewed_at=utcnow() if payload.reviewed else None,
        notes=payload.notes,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return mapping


async def list_alias_mappings(
    db: AsyncSession,
    source: str | None = None,
    entity_type: str | None = None,
    reviewed: bool | None = None,
) -> list[HistoricalAliasMapping]:
    stmt = select(HistoricalAliasMapping).order_by(HistoricalAliasMapping.created_at.desc())
    if source:
        stmt = stmt.where(HistoricalAliasMapping.source == source)
    if entity_type:
        stmt = stmt.where(HistoricalAliasMapping.entity_type == entity_type)
    if reviewed is not None:
        stmt = stmt.where(HistoricalAliasMapping.reviewed == reviewed)
    result = await db.execute(stmt)
    return list(result.scalars().all())
