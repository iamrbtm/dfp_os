from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class InventoryMovementType(StrEnum):
    ADJUSTMENT = "adjustment"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    RESERVATION = "reservation"
    RELEASE = "release"
    DEDUCTION = "deduction"
    RETURN = "return"


class InventoryMovement(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "inventory_movements"

    inventory_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_records.id"), nullable=True, index=True
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id"), nullable=True, index=True
    )
    from_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_locations.id"), nullable=True, index=True
    )
    to_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_locations.id"), nullable=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    movement_type: Mapped[InventoryMovementType] = mapped_column(
        Enum(InventoryMovementType, native_enum=False, length=40),
        nullable=False,
        index=True,
    )
    reference_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    inventory_record = relationship("InventoryRecord")
    actor = relationship("User")
