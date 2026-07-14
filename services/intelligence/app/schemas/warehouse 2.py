from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class WarehouseBuildResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    fact_rows: int
    product_summary_rows: int
    seasonal_summary_rows: int
    channel_summary_rows: int
    error_message: str | None


class ProductSalesSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_key: str
    product_name: str
    category_name: str | None
    total_units: Decimal
    total_net_sales_cents: int
    transaction_count: int
    active_months: int
    avg_units_per_active_month: Decimal
    avg_net_sales_cents_per_unit: int
    first_sale_date: date | None
    last_sale_date: date | None


class ProductSalesSummaryListResponse(BaseModel):
    items: list[ProductSalesSummaryResponse]


class ChannelPerformanceSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_name: str
    total_units: Decimal
    total_net_sales_cents: int
    transaction_count: int
    active_months: int


class ChannelPerformanceSummaryListResponse(BaseModel):
    items: list[ChannelPerformanceSummaryResponse]


class SeasonalProductPerformanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_key: str
    product_name: str
    sale_month: int
    total_units: Decimal
    total_net_sales_cents: int
    transaction_count: int


class SeasonalProductPerformanceListResponse(BaseModel):
    items: list[SeasonalProductPerformanceResponse]


class MarketAdvisorRequest(BaseModel):
    market_name: str = Field(min_length=1, max_length=255)
    market_date: date | None = None
    event_type: str | None = Field(default=None, max_length=120)
    expected_foot_traffic: int | None = Field(default=None, ge=0)
    booth_fee_cents: int | None = Field(default=None, ge=0)
    inventory_by_product_key: dict[str, int] = Field(default_factory=dict)
    max_products: int = Field(default=12, ge=1, le=50)


class MarketAdvisorRecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rank: int
    product_key: str
    product_name: str
    category_name: str | None
    suggested_quantity: int
    suggested_print_quantity: int
    expected_revenue_cents: int
    risk_level: str
    score: Decimal
    rationale: str
    evidence: dict


class MarketAdvisorRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    market_name: str
    market_date: date | None
    event_type: str | None
    max_products: int
    status: str
    input_context: dict
    created_at: datetime
    recommendations: list[MarketAdvisorRecommendationResponse]
