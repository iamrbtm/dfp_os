from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportSource(StrEnum):
    SQUARE_CSV = "square_csv"
    LEGACY_MARIADB = "legacy_mariadb"
    LEGACY_MARIADB_JSON = "legacy_mariadb_json"
    DFPOS_SNAPSHOT = "dfpos_snapshot"


class ImportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TableReviewDecision(StrEnum):
    PENDING = "pending"
    KEEP = "keep"
    EXCLUDE = "exclude"
    DELETE_STAGING = "delete_staging"


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


class PromotedLegacyTable(Base):
    __tablename__ = "promoted_legacy_tables"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    table_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    import_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    review_state_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    target_entity_type: Mapped[str] = mapped_column(String(40), nullable=False, default="other", index=True)
    column_names: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_data: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("import_batch_id", "table_name", name="uq_promoted_legacy_table_batch_table"),
    )


class LegacyImportRowStage(Base):
    __tablename__ = "legacy_import_row_stage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    table_manifest_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_table_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_primary_key_value: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    source_row_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    column_names: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    import_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("import_batch_id", "source_table_name", "row_number", name="uq_legacy_row_stage_batch_table_row"),
    )


class LegacyTableReviewState(Base):
    __tablename__ = "legacy_table_review_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    table_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    decision: Mapped[str] = mapped_column(String(40), nullable=False, default=TableReviewDecision.PENDING.value, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SquareItemRaw(Base):
    __tablename__ = "square_item_raw"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    time_zone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qty: Mapped[str | None] = mapped_column(String(40), nullable=True)
    price_point_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    modifiers_applied: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gross_sales_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discounts_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    net_sales_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dining_option: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    count: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gtin: Mapped[str | None] = mapped_column(String(80), nullable=True)
    itemization_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fulfillment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    card_brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sensitive_fields_present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class LegacyMariaDbTableSnapshot(Base):
    __tablename__ = "legacy_mariadb_table_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    estimated_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    columns: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    primary_key_columns: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class LegacyTableManifest(Base):
    __tablename__ = "legacy_table_manifests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    import_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    estimated_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    columns: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    primary_key_columns: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    import_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    import_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SalesFactLine(Base):
    __tablename__ = "sales_fact_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_row_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sale_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sale_month: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    product_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    gross_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ProductSalesSummary(Base):
    __tablename__ = "product_sales_summaries"

    product_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_units: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    total_net_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_units_per_active_month: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    avg_net_sales_cents_per_unit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class SeasonalProductPerformance(Base):
    __tablename__ = "seasonal_product_performance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sale_month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    total_units: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    total_net_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("product_key", "sale_month", name="uq_seasonal_product_key_month"),
    )


class ChannelPerformanceSummary(Base):
    __tablename__ = "channel_performance_summaries"

    channel_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    total_units: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    total_net_sales_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class HistoricalAliasMapping(Base):
    __tablename__ = "historical_alias_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_value: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=1.0)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class WarehouseBuild(Base):
    __tablename__ = "warehouse_builds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fact_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_summary_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seasonal_summary_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    channel_summary_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    build_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    document_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_set: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_doc_index"),
    )


class DecisionOutcome(Base):
    __tablename__ = "decision_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recommendation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    decision_type: Mapped[str] = mapped_column(String(80), nullable=False, default="market_advisor", index=True)
    user_action: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome_status: Mapped[str] = mapped_column(String(80), nullable=False)
    actual_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_revenue_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AskDfpRun(Base):
    __tablename__ = "ask_dfp_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MarketAdvisorRun(Base):
    __tablename__ = "market_advisor_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    market_name: Mapped[str] = mapped_column(String(255), nullable=False)
    market_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    max_products: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    input_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MarketAdvisorRecommendation(Base):
    __tablename__ = "market_advisor_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    product_key: Mapped[str] = mapped_column(String(255), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suggested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    suggested_print_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_revenue_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entity_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class NormalizedEntity(Base):
    __tablename__ = "normalized_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    promoted_table_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    original_table_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    original_primary_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_value: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_value: Mapped[str | None] = mapped_column("status", String(40), nullable=True)
    source_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
