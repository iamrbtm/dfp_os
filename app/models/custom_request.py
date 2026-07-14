from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin
from app.models.business import Business


class CustomRequestStatus(StrEnum):
    NEW = "new"
    QUOTED = "quoted"
    APPROVED = "approved"
    DEPOSIT_COLLECTED = "deposit_collected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class CustomRequest(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "custom_requests"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_image_paths: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_budget: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CustomRequestStatus] = mapped_column(
        Enum(CustomRequestStatus, native_enum=False, length=40),
        default=CustomRequestStatus.NEW,
        nullable=False,
        index=True,
    )
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_to_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    source: Mapped[str | None] = mapped_column(String(40), default="website", nullable=True)

    business: Mapped[Business | None] = relationship(back_populates="custom_requests")
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tax: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, default=Decimal(0))
    discount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, default=Decimal(0))
    total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    amount_paid: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, default=Decimal(0))

    converted_to_order = relationship("Order", foreign_keys=[converted_to_order_id])
    customer = relationship("Customer", back_populates="custom_requests")
