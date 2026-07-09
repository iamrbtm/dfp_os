from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentCreate(BaseModel):
    source: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=255)
    document_type: str = Field(min_length=1, max_length=80)
    source_ref: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1)
    metadata: dict | None = None


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    title: str
    document_type: str
    source_ref: str | None
    content: str
    document_metadata: dict | None
    created_at: datetime
    updated_at: datetime


class KnowledgeChunkSearchResult(BaseModel):
    document_id: str
    title: str
    document_type: str
    source: str
    source_ref: str | None
    chunk_id: str
    chunk_index: int
    text: str
    score: int


class KnowledgeSearchResponse(BaseModel):
    items: list[KnowledgeChunkSearchResult]


class AskDfpRequest(BaseModel):
    question: str = Field(min_length=3)
    allowed_tools: list[str] = Field(
        default_factory=lambda: ["product_summary", "seasonal_summary", "channel_summary", "knowledge_search"]
    )
    limit: int = Field(default=5, ge=1, le=20)


class AskDfpResponse(BaseModel):
    id: str
    question: str
    answer: str
    allowed_tools: list[str]
    evidence: list[dict]
    created_at: datetime


class DecisionOutcomeCreate(BaseModel):
    recommendation_id: str | None = None
    run_id: str | None = None
    decision_type: str = Field(default="market_advisor", max_length=80)
    user_action: str = Field(min_length=1, max_length=80)
    outcome_status: str = Field(min_length=1, max_length=80)
    actual_units: int | None = Field(default=None, ge=0)
    actual_revenue_cents: int | None = Field(default=None, ge=0)
    notes: str | None = None
    created_by: str | None = Field(default=None, max_length=120)


class DecisionOutcomeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recommendation_id: str | None
    run_id: str | None
    decision_type: str
    user_action: str
    outcome_status: str
    actual_units: int | None
    actual_revenue_cents: int | None
    notes: str | None
    created_by: str | None
    created_at: datetime


class DecisionOutcomeListResponse(BaseModel):
    items: list[DecisionOutcomeResponse]
