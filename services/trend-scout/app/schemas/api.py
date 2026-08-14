from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportSummary(BaseModel):
    id: int
    report_date: datetime
    summary: str
    top_opportunities: list[Any] = Field(default_factory=list)
    growing_categories: list[Any] = Field(default_factory=list)
    declining_trends: list[Any] = Field(default_factory=list)
    scoring_version: str
    business_id: int | None = None
    run_id: str | None = None
    pipeline_metadata: dict[str, Any] = Field(default_factory=dict)
    pipeline_meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class ReportListResponse(BaseModel):
    items: list[ReportSummary]
    total: int


class OpportunityScore(BaseModel):
    id: int
    report_id: int
    keyword: str
    source: str
    score: float
    title: str | None = None
    candidate_type: str = "potential"
    product_id: int | None = None
    opportunity_score: int
    action: str
    rank: int | None = None
    recommended_action: str
    velocity: float
    trend_velocity: int
    momentum: float
    purchase_intent: int
    price_resilience: int = 0
    low_saturation: int = 0
    local_fit: int = 0
    production_fit: int = 0
    license_risk: int = 0
    license_status: str | None = None
    local_relevance: float
    inventory_available: int | None = None
    base_price: float | None = None
    sources: list[str] = Field(default_factory=list)
    match_confidence: float | None = None
    dismissed: bool
    score_breakdown: dict[str, Any] = Field(default_factory=dict)


class OpportunityListResponse(BaseModel):
    items: list[OpportunityScore]
    total: int


class OpportunityActionRequest(BaseModel):
    action: str


class SourceHealthRecord(BaseModel):
    id: int
    report_id: int | None = None
    source: str
    status: str
    keyword: str | None = None
    item_count: int = 0
    error_message: str | None = None
    throttled: bool = False
    throttle_reason: str | None = None
    scraped_at: datetime


class SourceHealthListResponse(BaseModel):
    items: list[SourceHealthRecord]
    total: int


class WeightEntry(BaseModel):
    group: str
    key: str
    value: float
    description: str | None = None


class WeightListResponse(BaseModel):
    items: list[WeightEntry]
    total: int


class WeightSaveRequest(BaseModel):
    entries: list[WeightEntry]


class PipelineRunRequest(BaseModel):
    trigger: str = "manual"
    run_id: str | None = None


class PipelineRunResponse(BaseModel):
    accepted: bool
    run_id: str
    task_id: str | None = None
    status: str


class PipelineStatusResponse(BaseModel):
    run_id: str
    state: str
    completed_step: str | None = None
    progress: float | None = None


class CalibrationRunRequest(BaseModel):
    trigger: str = "manual"
    lookback_reports: int = 12


class CalibrationRunResponse(BaseModel):
    accepted: bool
    trigger: str
    lookback_reports: int


class BacktestRunRequest(BaseModel):
    lookback_reports: int = 12
    sales_window_days: int = 60


class BacktestRunResponse(BaseModel):
    status: str
    report_count: int
    summary: dict[str, Any]
    predictions: list[dict[str, Any]] = Field(default_factory=list)


class SettingsSourceToggleRequest(BaseModel):
    source: str
    enabled: bool


class SettingsSourceToggleResponse(BaseModel):
    source: str
    enabled: bool
