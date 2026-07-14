from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class PosSessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    VOIDED = "voided"


class PosSaleStatus(StrEnum):
    COMPLETED = "completed"
    VOIDED = "voided"
    REFUNDED = "refunded"


class PosSaleItemType(StrEnum):
    PRODUCT = "product"
    CUSTOM_ITEM = "custom_item"
    CUSTOM_DEPOSIT = "custom_deposit"
    DISCOUNT = "discount"
    FEE = "fee"


def generate_pos_session_number() -> str:
    short = uuid.uuid4().hex[:8].upper()
    return f"POS-{short}"


def generate_pos_sale_number() -> str:
    short = uuid.uuid4().hex[:8].upper()
    return f"SALE-{short}"


class PosSession(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "pos_sessions"

    session_number: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True, default=generate_pos_session_number
    )
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    opened_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    closed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    inventory_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_locations.id"), nullable=True, index=True
    )
    status: Mapped[PosSessionStatus] = mapped_column(
        Enum(PosSessionStatus, native_enum=False, length=20),
        default=PosSessionStatus.OPEN,
        nullable=False,
        index=True,
    )
    opening_cash: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    closing_cash: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    cash_difference: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    opened_by = relationship("User", foreign_keys=[opened_by_user_id])
    closed_by = relationship("User", foreign_keys=[closed_by_user_id])
    inventory_location = relationship("InventoryLocation")
    sales = relationship(
        "PosSale",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PosSale.id",
    )


class PosSale(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "pos_sales"

    pos_session_id: Mapped[int] = mapped_column(
        ForeignKey("pos_sessions.id"), nullable=False, index=True
    )
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    sale_number: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True, default=generate_pos_sale_number
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    amount_received: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    change_due: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    status: Mapped[PosSaleStatus] = mapped_column(
        Enum(PosSaleStatus, native_enum=False, length=20),
        default=PosSaleStatus.COMPLETED,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    session = relationship("PosSession", back_populates="sales")
    order = relationship("Order")
    customer = relationship("Customer")
    items = relationship(
        "PosSaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="PosSaleItem.id",
    )


class PosSaleItem(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "pos_sale_items"

    pos_sale_id: Mapped[int] = mapped_column(
        ForeignKey("pos_sales.id"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    item_type: Mapped[PosSaleItemType] = mapped_column(
        Enum(PosSaleItemType, native_enum=False, length=20),
        default=PosSaleItemType.PRODUCT,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    custom_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    sale = relationship("PosSale", back_populates="items")
    product = relationship("Product")
