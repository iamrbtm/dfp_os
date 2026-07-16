from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin
from app.models.business import Business


class PrepTaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REOPENED = "reopened"
    CANCELED = "canceled"


class PrepTaskCategory(StrEnum):
    TODO = "todo"
    MARKETING = "marketing"
    APPLICATION = "application"
    PAYMENT = "payment"
    PACKING = "packing"
    FOLLOW_UP = "follow_up"
    INVENTORY = "inventory"
    REPRINT = "reprint"
    SUPPLY = "supply"
    CASH_BOX = "cash_box"
    SIGNAGE = "signage"
    PAYMENT_DEVICE = "payment_device"
    STAFFING = "staffing"
    GENERAL = "general"


class FollowUpType(StrEnum):
    CUSTOM_LEAD = "custom_lead"
    REQUESTED_COLOR = "requested_color"
    REQUESTED_PRODUCT = "requested_product"
    UNPAID_DEPOSIT = "unpaid_deposit"
    PICKUP_REMINDER = "pickup_reminder"
    THANK_YOU = "thank_you"
    QUOTE_FOLLOW_UP = "quote_follow_up"


class PrepTaskTemplate(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "prep_task_templates"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[PrepTaskCategory] = mapped_column(
        Enum(PrepTaskCategory, native_enum=False, length=40),
        default=PrepTaskCategory.GENERAL,
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    default_due_days_before: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    default_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped[Business | None] = relationship(back_populates="prep_task_templates")


class PrepTask(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "prep_tasks"

    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("prep_task_templates.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[PrepTaskCategory] = mapped_column(
        Enum(PrepTaskCategory, native_enum=False, length=40),
        default=PrepTaskCategory.GENERAL,
        nullable=False,
        index=True,
    )
    status: Mapped[PrepTaskStatus] = mapped_column(
        Enum(PrepTaskStatus, native_enum=False, length=40),
        default=PrepTaskStatus.OPEN,
        nullable=False,
        index=True,
    )
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    related_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    related_custom_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_requests.id"), nullable=True, index=True
    )
    related_pos_sale_id: Mapped[int | None] = mapped_column(
        ForeignKey("pos_sales.id"), nullable=True, index=True
    )

    business: Mapped[Business | None] = relationship(back_populates="prep_tasks")
    market = relationship("Market")
    template = relationship("PrepTaskTemplate")
    assigned_user = relationship("User")
    customer = relationship("Customer")
    related_order = relationship("Order")
    related_custom_request = relationship("CustomRequest")
    related_pos_sale = relationship("PosSale")
