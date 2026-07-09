from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


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
    default_due_days_before: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    default_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PrepTask(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "prep_tasks"

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

    market = relationship("Market")
    template = relationship("PrepTaskTemplate")
    assigned_user = relationship("User")
