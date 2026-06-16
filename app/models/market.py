from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class MarketStatus(StrEnum):
    INTERESTED = "interested"
    APPLIED = "applied"
    ACCEPTED = "accepted"
    WAITLISTED = "waitlisted"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELED = "canceled"
    NOT_WORTH_REPEATING = "not_worth_repeating"
    REPEAT = "repeat"


class Market(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "markets"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    location_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    booth_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, default=0)
    application_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, default=0)
    status: Mapped[MarketStatus] = mapped_column(
        Enum(MarketStatus, native_enum=False, length=40),
        default=MarketStatus.INTERESTED,
        nullable=False,
        index=True,
    )
    expected_traffic: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actual_revenue: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, default=0)
    actual_profit: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    packing_list = relationship(
        "MarketPackingList", back_populates="market", cascade="all, delete-orphan"
    )


    @property
    def total_booth_cost(self) -> Decimal:
        return (self.booth_fee or Decimal(0)) + (self.application_fee or Decimal(0))

    @property
    def calculated_revenue(self) -> Decimal:
        from app.models import Order
        result = db.session.query(func.sum(Order.total)).filter(
            Order.market_id == self.id,
            Order.deleted_at.is_(None),
        ).scalar()
        return result or Decimal(0)

    @property
    def calculated_profit(self) -> Decimal:
        from app.models import Expense
        expenses = db.session.query(func.sum(Expense.amount)).filter(
            Expense.related_market_id == self.id,
        ).scalar() or Decimal(0)
        return self.calculated_revenue - expenses - self.total_booth_cost

    @property
    def profit_margin_pct(self) -> Decimal | None:
        rev = self.calculated_revenue
        if rev and rev > 0:
            return self.calculated_profit / rev * Decimal(100)
        return None


class MarketPackingList(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_packing_lists"

    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id"), nullable=True, index=True
    )
    planned_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    packed_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sold_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    returned_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    market = relationship("Market", back_populates="packing_list")
    product = relationship("Product")
    variant = relationship("ProductVariant")
