from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class PrinterStatus(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    PRINTING = "printing"
    MAINTENANCE = "maintenance"
    BROKEN = "broken"
    RETIRED = "retired"


class AMSUnitType(StrEnum):
    AMS_LITE = "ams_lite"
    STANDARD_AMS = "standard_ams"


class AMSUnitStatus(StrEnum):
    ACTIVE = "active"
    ASSIGNED = "assigned"
    MAINTENANCE = "maintenance"
    BROKEN = "broken"
    RETIRED = "retired"


class Printer(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "printers"

    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    status: Mapped[PrinterStatus] = mapped_column(
        Enum(PrinterStatus, native_enum=False, length=40),
        default=PrinterStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    has_ams: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_nozzle_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    maintenance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_print_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    ams_units = relationship("AMSUnit", back_populates="assigned_printer")


class AMSUnit(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "ams_units"

    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    type: Mapped[AMSUnitType] = mapped_column(
        Enum(AMSUnitType, native_enum=False, length=40),
        default=AMSUnitType.AMS_LITE,
        nullable=False,
    )
    status: Mapped[AMSUnitStatus] = mapped_column(
        Enum(AMSUnitStatus, native_enum=False, length=40),
        default=AMSUnitStatus.ACTIVE,
        nullable=False,
    )
    assigned_printer_id: Mapped[int | None] = mapped_column(
        ForeignKey("printers.id"), nullable=True, index=True
    )
    slot_count: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    assigned_printer = relationship("Printer", back_populates="ams_units")
