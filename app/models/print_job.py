from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class PrintJobStatus(StrEnum):
    QUEUED = "queued"
    PRINTING = "printing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PrintJob(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "print_jobs"

    order_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_items.id"), nullable=True, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True
    )
    printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("printers.id"), nullable=True, index=True
    )
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[PrintJobStatus] = mapped_column(
        Enum(PrintJobStatus, native_enum=False, length=40),
        default=PrintJobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filament_used_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trend_opportunity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    order_item = relationship("OrderItem", back_populates="print_jobs")
    product = relationship("Product")
    printer = relationship("Printer")
    assigned_to = relationship("User")
    failure_autopsies = relationship(
        "PrintFailureAutopsy",
        back_populates="print_job",
        cascade="all, delete-orphan",
        order_by="PrintFailureAutopsy.created_at.desc()",
    )
