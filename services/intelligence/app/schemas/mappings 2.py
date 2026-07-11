from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AliasMappingCreate(BaseModel):
    source: str = Field(min_length=1, max_length=40)
    entity_type: str = Field(min_length=1, max_length=40)
    source_value: str = Field(min_length=1, max_length=255)
    normalized_value: str | None = Field(default=None, max_length=255)
    target_entity_type: str | None = Field(default=None, max_length=40)
    target_entity_id: str | None = Field(default=None, max_length=120)
    target_display_name: str | None = Field(default=None, max_length=255)
    match_confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    reviewed: bool = False
    reviewed_by: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class AliasMappingReview(BaseModel):
    target_entity_type: str | None = Field(default=None, max_length=40)
    target_entity_id: str | None = Field(default=None, max_length=120)
    target_display_name: str | None = Field(default=None, max_length=255)
    match_confidence: Decimal = Field(ge=0, le=1)
    reviewed_by: str = Field(min_length=1, max_length=120)
    notes: str | None = None


class AliasMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    entity_type: str
    source_value: str
    normalized_value: str | None
    target_entity_type: str | None
    target_entity_id: str | None
    target_display_name: str | None
    match_confidence: Decimal
    reviewed: bool
    reviewed_by: str | None
    reviewed_at: datetime | None
    notes: str | None


class AliasMappingListResponse(BaseModel):
    items: list[AliasMappingResponse]
