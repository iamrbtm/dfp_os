from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class PrintFailureCategory(StrEnum):
    SPAGHETTI = "spaghetti"
    ADHESION = "adhesion"
    CLOG = "clog"
    LAYER_SHIFT = "layer_shift"
    SUPPORT_FAILURE = "support_failure"
    FILAMENT_ISSUE = "filament_issue"
    POWER_OR_USER_INTERRUPTION = "power_or_user_interruption"
    SLICER_SETTINGS = "slicer_settings"
    UNKNOWN = "unknown"


class PrintFailureSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PrintFailureAutopsy(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "print_failure_autopsies"

    print_job_id: Mapped[int] = mapped_column(
        ForeignKey("print_jobs.id"), nullable=False, index=True
    )
    printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("printers.id"), nullable=True, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True
    )
    filament_spool_id: Mapped[int | None] = mapped_column(
        ForeignKey("filament_spools.id"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    model_asset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    category: Mapped[PrintFailureCategory] = mapped_column(
        Enum(PrintFailureCategory, native_enum=False, length=60),
        default=PrintFailureCategory.UNKNOWN,
        nullable=False,
        index=True,
    )
    severity: Mapped[PrintFailureSeverity] = mapped_column(
        Enum(PrintFailureSeverity, native_enum=False, length=40),
        default=PrintFailureSeverity.MEDIUM,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    maintenance_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    print_job = relationship("PrintJob", back_populates="failure_autopsies")
    printer = relationship("Printer")
    product = relationship("Product")
    filament_spool = relationship("FilamentSpool")
    user = relationship("User")
