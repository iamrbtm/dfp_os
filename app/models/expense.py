from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class ExpenseCategory(StrEnum):
    FILAMENT = "filament"
    PRINTER_PARTS = "printer_parts"
    TOOLS = "tools"
    BOOTH_FEES = "booth_fees"
    PACKAGING = "packaging"
    SHIPPING = "shipping"
    SOFTWARE = "software"
    ADVERTISING = "advertising"
    VEHICLE_TRAVEL = "vehicle_travel"
    OFFICE_SUPPLIES = "office_supplies"
    LICENSES_FEES = "licenses_fees"
    OTHER = "other"


class Expense(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "expenses"

    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    vendor: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(
        Enum(ExpenseCategory, native_enum=False, length=40),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    related_market_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    related_order_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    receipt_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    receipt_file_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    tax_deductible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
