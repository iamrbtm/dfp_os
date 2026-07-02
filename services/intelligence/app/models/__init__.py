from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Integer, JSON, Numeric, String, Text, UniqueConstraint
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
