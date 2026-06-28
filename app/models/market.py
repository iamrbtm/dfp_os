from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, JSON, Numeric, String, Text, Time, func
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


class MarketTaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELED = "canceled"


class MarketTaskType(StrEnum):
    TODO = "todo"
    MARKETING = "marketing"
    APPLICATION = "application"
    PAYMENT = "payment"
    PACKING = "packing"
    FOLLOW_UP = "follow_up"


class MarketTimelineEventType(StrEnum):
    SETUP = "setup"
    MARKET_HOURS = "market_hours"
    LOAD_IN = "load_in"
    LOAD_OUT = "load_out"
    DEADLINE = "deadline"
    REMINDER = "reminder"
    OTHER = "other"


class MarketHotelBookingStatus(StrEnum):
    PLANNED = "planned"
    BOOKED = "booked"
    CANCELED = "canceled"
    COMPLETED = "completed"


class MarketDocumentType(StrEnum):
    APPLICATION = "application"
    PERMIT = "permit"
    RECEIPT = "receipt"
    MAP = "map"
    CONTRACT = "contract"
    MARKETING = "marketing"
    OTHER = "other"


class Market(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "markets"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    location_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    application_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    application_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fee_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    booth_location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    booth_size: Mapped[str | None] = mapped_column(String(80), nullable=True)
    power_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wifi_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    food_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    load_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    load_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    load_in_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    load_out_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    timeline_events = relationship(
        "MarketTimelineEvent", back_populates="market", cascade="all, delete-orphan"
    )
    tasks = relationship("MarketTask", back_populates="market", cascade="all, delete-orphan")
    weather_snapshots = relationship(
        "MarketWeatherSnapshot", back_populates="market", cascade="all, delete-orphan"
    )
    hotel_bookings = relationship(
        "MarketHotelBooking", back_populates="market", cascade="all, delete-orphan"
    )
    documents = relationship("MarketDocument", back_populates="market", cascade="all, delete-orphan")

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
    planned_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    packed_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    sold_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    returned_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    market = relationship("Market", back_populates="packing_list")
    product = relationship("Product")


class MarketTimelineEvent(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_timeline_events"

    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_type: Mapped[MarketTimelineEventType] = mapped_column(
        Enum(MarketTimelineEventType, native_enum=False, length=40),
        default=MarketTimelineEventType.OTHER,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    market = relationship("Market", back_populates="timeline_events")


class MarketTask(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_tasks"

    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[MarketTaskType] = mapped_column(
        Enum(MarketTaskType, native_enum=False, length=40),
        default=MarketTaskType.TODO,
        nullable=False,
        index=True,
    )
    status: Mapped[MarketTaskStatus] = mapped_column(
        Enum(MarketTaskStatus, native_enum=False, length=40),
        default=MarketTaskStatus.OPEN,
        nullable=False,
        index=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    market = relationship("Market", back_populates="tasks")


class MarketWeatherSnapshot(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_weather_snapshots"

    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(80), default="weather.gov", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    temperature: Mapped[int | None] = mapped_column(Integer, nullable=True)
    short_forecast: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detailed_forecast: Mapped[str | None] = mapped_column(Text, nullable=True)
    precipitation_probability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wind_speed: Mapped[str | None] = mapped_column(String(80), nullable=True)
    wind_direction: Mapped[str | None] = mapped_column(String(30), nullable=True)
    alert_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    market = relationship("Market", back_populates="weather_snapshots")


class MarketHotelBooking(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_hotel_bookings"

    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    hotel_name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    check_in_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    check_out_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmation_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[MarketHotelBookingStatus] = mapped_column(
        Enum(MarketHotelBookingStatus, native_enum=False, length=40),
        default=MarketHotelBookingStatus.PLANNED,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    market = relationship("Market", back_populates="hotel_bookings")


class MarketDocument(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_documents"

    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_type: Mapped[MarketDocumentType] = mapped_column(
        Enum(MarketDocumentType, native_enum=False, length=40),
        default=MarketDocumentType.OTHER,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    market = relationship("Market", back_populates="documents")
    uploaded_by = relationship("User")
