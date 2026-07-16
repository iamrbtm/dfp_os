from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class PickupLocationType(StrEnum):
    MARKET = "market"
    PORCH = "porch"
    HANDOFF = "handoff"
    OTHER = "other"


class PickupSlotStatus(StrEnum):
    OPEN = "open"
    FULL = "full"
    CLOSED = "closed"
    CANCELED = "canceled"


class PickupStatus(StrEnum):
    SCHEDULED = "scheduled"
    READY = "ready"
    HANDED_OFF = "handed_off"
    NO_SHOW = "no_show"
    CANCELED = "canceled"


class PickupLocation(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "pickup_locations"

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    location_type: Mapped[PickupLocationType] = mapped_column(
        Enum(PickupLocationType, native_enum=False, length=40),
        default=PickupLocationType.PORCH,
        nullable=False,
        index=True,
    )
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    slots = relationship("PickupSlot", back_populates="location", cascade="all, delete-orphan")


class PickupSlot(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "pickup_slots"

    location_id: Mapped[int] = mapped_column(ForeignKey("pickup_locations.id"), nullable=False, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    capacity: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    status: Mapped[PickupSlotStatus] = mapped_column(
        Enum(PickupSlotStatus, native_enum=False, length=40),
        default=PickupSlotStatus.OPEN,
        nullable=False,
        index=True,
    )
    public_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    location = relationship("PickupLocation", back_populates="slots")
    market = relationship("Market")
    orders = relationship("Order", back_populates="pickup_slot")
    custom_requests = relationship("CustomRequest", back_populates="pickup_slot")

    @property
    def scheduled_count(self) -> int:
        order_count = len([order for order in self.orders if order.pickup_status != PickupStatus.CANCELED])
        request_count = len(
            [request for request in self.custom_requests if request.pickup_status != PickupStatus.CANCELED]
        )
        return order_count + request_count

    @property
    def available_capacity(self) -> int:
        return max(0, self.capacity - self.scheduled_count)
