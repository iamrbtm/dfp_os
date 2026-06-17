from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class ReceiptStatus(StrEnum):
    UPLOADED = "uploaded"
    PREPROCESSING = "preprocessing"
    OCR_PROCESSING = "ocr_processing"
    AI_EXTRACTING = "ai_extracting"
    NEEDS_REVIEW = "needs_review"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    PROCESSING_FAILED = "processing_failed"


class ReceiptSourceType(StrEnum):
    UPLOAD = "upload"
    CAMERA = "camera"
    EMAIL_IMPORT = "email_import"
    MANUAL = "manual"


class AllocationType(StrEnum):
    MARKET = "market"
    CUSTOM_JOB = "custom_job"
    INVENTORY = "inventory"
    GENERAL_EXPENSE = "general_expense"
    PERSONAL_EXCLUDED = "personal_excluded"


class AdjustmentType(StrEnum):
    TAX = "tax"
    FEE = "fee"
    DISCOUNT = "discount"
    DEPOSIT = "deposit"
    TIP = "tip"
    ROUNDING = "rounding"


class AllocationMethod(StrEnum):
    EXACT = "exact"
    TAXABLE_PROPORTIONAL = "taxable_proportional"
    SUBTOTAL_PROPORTIONAL = "subtotal_proportional"
    CATEGORY_RULE = "category_rule"
    MANUAL = "manual"
    UNALLOCATED = "unallocated"


class Receipt(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "receipts"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[ReceiptStatus] = mapped_column(
        Enum(ReceiptStatus, native_enum=False, length=40),
        default=ReceiptStatus.UPLOADED,
        nullable=False,
        index=True,
    )
    original_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preview_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumbnail_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[ReceiptSourceType] = mapped_column(
        Enum(ReceiptSourceType, native_enum=False, length=40),
        default=ReceiptSourceType.UPLOAD,
    )
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_ocr_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_extracted_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_reviewed_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parser_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence_overall: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    low_confidence_flags: Mapped[str | None] = mapped_column(Text, nullable=True)
    merchant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merchant_normalized_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    store_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    store_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(60), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(60), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    transaction_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    register_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cashier_name_or_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    date_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    timezone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tax_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    discount_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tip_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    deposit_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    rounding_adjustment: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    grand_total: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True, index=True
    )
    payment_method: Mapped[str | None] = mapped_column(String(60), nullable=True)
    payment_card_brand: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payment_card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    duplicate_group_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    duplicate_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    line_items = relationship(
        "ReceiptLineItem",
        back_populates="receipt",
        cascade="all, delete-orphan",
    )
    adjustments = relationship(
        "ReceiptAdjustmentAllocation",
        back_populates="receipt",
        cascade="all, delete-orphan",
    )
    user = relationship("User", foreign_keys=[user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    rejected_by = relationship("User", foreign_keys=[rejected_by_id])


class ReceiptLineItem(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "receipt_line_items"

    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id"), nullable=False, index=True
    )
    row_order: Mapped[int] = mapped_column(Integer, default=0)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    normalized_description: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    upc: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    unit_of_measure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    line_subtotal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    line_discount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    line_tax: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    line_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    line_deposit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    line_tip_allocation: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    taxable_status: Mapped[str] = mapped_column(String(20), default="unknown")
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_description: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    confidence_price: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    confidence_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )
    confidence_tax: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    is_inventory_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    is_personal_or_excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    receipt = relationship("Receipt", back_populates="line_items")
    allocations = relationship(
        "ReceiptLineAllocation",
        back_populates="line_item",
        cascade="all, delete-orphan",
    )


class ReceiptLineAllocation(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "receipt_line_allocations"

    receipt_line_item_id: Mapped[int] = mapped_column(
        ForeignKey("receipt_line_items.id"), nullable=False, index=True
    )
    allocation_type: Mapped[AllocationType] = mapped_column(
        Enum(AllocationType, native_enum=False, length=40),
        nullable=False,
    )
    market_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    custom_job_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    inventory_item_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    expense_category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    quantity_allocated: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    line_item = relationship("ReceiptLineItem", back_populates="allocations")


class ReceiptAdjustmentAllocation(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "receipt_adjustment_allocations"

    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id"), nullable=False, index=True
    )
    adjustment_type: Mapped[AdjustmentType] = mapped_column(
        Enum(AdjustmentType, native_enum=False, length=40),
        nullable=False,
    )
    allocation_method: Mapped[AllocationMethod] = mapped_column(
        Enum(AllocationMethod, native_enum=False, length=40),
        nullable=False,
    )
    source_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    allocated_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    unallocated_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    calculation_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    receipt = relationship("Receipt", back_populates="adjustments")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReceiptAuditEvent(PrimaryKeyMixin, db.Model):
    __tablename__ = "receipt_audit_events"

    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    receipt = relationship("Receipt")
    user = relationship("User", foreign_keys=[user_id])
