from __future__ import annotations

import uuid
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


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PRINTING = "printing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderSource(StrEnum):
    POS = "pos"
    ONLINE = "online"
    CUSTOM = "custom"
    MANUAL = "manual"
    MARKET = "market"


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD_EXTERNAL = "card_external"
    VENMO = "venmo"
    CASH_APP = "cash_app"
    APPLE_PAY = "apple_pay"
    OTHER = "other"


def generate_order_number() -> str:
    short = uuid.uuid4().hex[:8].upper()
    return f"DFP-{short}"


class Order(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "orders"

    order_number: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True, default=generate_order_number
    )
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False, length=40),
        default=OrderStatus.PENDING,
        nullable=False,
        index=True,
    )
    source: Mapped[OrderSource] = mapped_column(
        Enum(OrderSource, native_enum=False, length=40),
        default=OrderSource.MANUAL,
        nullable=False,
    )
    market_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    pos_session_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer", back_populates="orders")
    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
    )
    payments = relationship(
        "Payment",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="Payment.payment_date",
    )
    custom_requests = relationship(
        "CustomRequest",
        foreign_keys="CustomRequest.converted_to_order_id",
        back_populates="converted_to_order",
    )

    @property
    def balance_due(self) -> Decimal:
        return self.total - self.paid_amount


class OrderItem(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "order_items"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id"), nullable=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    is_custom_item: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    custom_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")
    variant = relationship("ProductVariant")
    print_jobs = relationship(
        "PrintJob", back_populates="order_item", cascade="all, delete-orphan"
    )


class Payment(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "payments"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, native_enum=False, length=40),
        default=PaymentMethod.CASH,
        nullable=False,
    )
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False
    )

    order = relationship("Order", back_populates="payments")
