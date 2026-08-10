from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class MarketInterestLevel(StrEnum):
    WATCHING = "watching"
    INTERESTED = "interested"
    PRIORITY = "priority"


class MarketRecurrenceFrequency(StrEnum):
    YEARLY = "yearly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    NONE = "none"


class MarketCategory(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_categories"

    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    listings = relationship(
        "MarketCatalogListing", back_populates="category", cascade="all, delete-orphan"
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class MarketCatalogListing(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_catalog_listings"

    # Identity
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True, index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_categories.id"), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Location
    location_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timing
    default_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    default_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="America/Chicago")

    # Recurrence
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rrule: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_occurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_occurrence_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Scale
    estimated_vendor_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_attendee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Amenities
    power_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wifi_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    food_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    restrooms_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    indoor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    covered_outdoor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outdoor: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parking_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Organizer contact
    organizer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    organizer_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    organizer_phone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    application_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    application_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    application_deadline_description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Rules / docs
    booth_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_documents: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tracking
    interest_level: Mapped[MarketInterestLevel] = mapped_column(
        Enum(MarketInterestLevel, native_enum=False, length=40),
        nullable=False,
        default=MarketInterestLevel.WATCHING,
        index=True,
    )

    # Business
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    category = relationship("MarketCategory", back_populates="listings")
    booth_tiers = relationship(
        "MarketCatalogBoothTier",
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="MarketCatalogBoothTier.sort_order",
    )
    booked_markets = relationship("Market", back_populates="catalog_listing")

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def booth_price_range(self) -> tuple[Decimal, Decimal] | None:
        prices = [t.price for t in self.booth_tiers if t.price is not None]
        if not prices:
            return None
        return min(prices), max(prices)


class MarketCatalogBoothTier(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_catalog_booth_tiers"

    listing_id: Mapped[int] = mapped_column(
        ForeignKey("market_catalog_listings.id"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    dimensions: Mapped[str | None] = mapped_column(String(80), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, default=0)
    corner_premium: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    listing = relationship("MarketCatalogListing", back_populates="booth_tiers")

    @property
    def display_price(self) -> str:
        if self.price is None:
            return "—"
        text = f"${self.price:,.2f}"
        if self.corner_premium is not None:
            text += f" (+${self.corner_premium:,.2f} corner)"
        return text