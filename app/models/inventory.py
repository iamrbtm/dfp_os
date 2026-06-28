from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class FilamentStatus(StrEnum):
    NEW = "new"
    ACTIVE = "active"
    LOW = "low"
    EMPTY = "empty"
    ARCHIVED = "archived"


class FilamentSpool(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "filament_spools"

    brand: Mapped[str] = mapped_column(String(160), nullable=False)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    material_type: Mapped[str] = mapped_column(String(120), nullable=False)
    color_name: Mapped[str] = mapped_column(String(120), nullable=False)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    spool_weight_grams: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    remaining_weight_grams: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    cost_per_spool: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    cost_per_gram: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0, nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(160), nullable=True)
    purchase_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    storage_location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[FilamentStatus] = mapped_column(
        Enum(FilamentStatus, native_enum=False, length=40),
        default=FilamentStatus.NEW,
        nullable=False,
    )
    reorder_threshold_grams: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class InventoryLocation(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "inventory_locations"

    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    inventory_records = relationship("InventoryRecord", back_populates="location")


class InventoryRecord(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "inventory_records"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "location_id",
            name="uq_inventory_records_product_location",
        ),
    )

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id"), nullable=True, index=True
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_locations.id"), nullable=False, index=True
    )
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_threshold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_target: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_counted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product = relationship("Product", back_populates="inventory_records")
    location = relationship("InventoryLocation", back_populates="inventory_records")

    @property
    def quantity_available(self) -> int:
        return self.quantity_on_hand - self.quantity_reserved
