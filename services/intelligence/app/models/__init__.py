from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportSource(StrEnum):
    SQUARE_CSV = "square_csv"
    LEGACY_MARIADB = "legacy_mariadb"
    DFPOS_SNAPSHOT = "dfpos_snapshot"


class ImportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AliasEntityType(StrEnum):
    PRODUCT = "product"
    VARIANT = "variant"
    CATEGORY = "category"
    CHANNEL = "channel"
    CUSTOMER = "customer"
    MARKET = "market"


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default=ImportStatus.PENDING.value, index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SquareItemRaw(Base):
    __tablename__ = "square_item_raw"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    date: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    time_zone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    item: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    qty: Mapped[str | None] = mapped_column(String(80), nullable=True)
    price_point_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    modifiers_applied: Mapped[str | None] = mapped_column(Text, nullable=True)
    gross_sales_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discounts_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    net_sales_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    payment_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    dining_option: Mapped[str | None] = mapped_column(String(120), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_reference_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    count: Mapped[str | None] = mapped_column(String(80), nullable=True)
    gtin: Mapped[str | None] = mapped_column(String(120), nullable=True)
    itemization_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fulfillment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    card_brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sensitive_fields_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("import_batch_id", "row_number", name="uq_square_item_raw_batch_row"),)


class LegacyMariaDbTableSnapshot(Base):
    __tablename__ = "legacy_mariadb_table_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    estimated_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    columns: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    primary_key_columns: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class HistoricalAliasMapping(Base):
    __tablename__ = "historical_alias_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_value: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_value: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    target_entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    target_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("source", "entity_type", "source_value", name="uq_historical_alias_source_value"),)


class WarehouseBuild(Base):
    __tablename__ = "warehouse_builds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default=ImportStatus.RUNNING.value, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fact_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_summary_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seasonal_summary_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    channel_summary_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    build_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


class SalesFactLine(Base):
    __tablename__ = "sales_fact_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sale_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    sale_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sale_month: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    variant_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    gross_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("source", "source_row_id", name="uq_sales_fact_source_row"),)


class ProductSalesSummary(Base):
    __tablename__ = "product_sales_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    total_units: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    total_net_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_units_per_active_month: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    avg_net_sales_cents_per_unit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_sale_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("product_key", name="uq_product_sales_summary_product_key"),)


class SeasonalProductPerformance(Base):
    __tablename__ = "seasonal_product_performance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sale_month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    total_units: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    total_net_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("product_key", "sale_month", name="uq_seasonal_product_month"),)


class ChannelPerformanceSummary(Base):
    __tablename__ = "channel_performance_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    total_units: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    total_net_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("channel_name", name="uq_channel_performance_channel"),)


class MarketAdvisorRun(Base):
    __tablename__ = "market_advisor_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    market_name: Mapped[str] = mapped_column(String(255), nullable=False)
    market_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    event_type: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    max_products: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed", index=True)
    input_context: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MarketAdvisorRecommendation(Base):
    __tablename__ = "market_advisor_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    product_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suggested_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suggested_print_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_revenue_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("run_id", "rank", name="uq_market_advisor_run_rank"),)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    document_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_set: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_document_index"),)


class AskDfpRun(Base):
    __tablename__ = "ask_dfp_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class DecisionOutcome(Base):
    __tablename__ = "decision_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recommendation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    decision_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    user_action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    outcome_status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actual_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_revenue_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
