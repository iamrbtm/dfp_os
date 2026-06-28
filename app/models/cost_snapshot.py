from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class CostSnapshotConfidence(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostSnapshot(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "cost_snapshots"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    filament_spool_id: Mapped[int | None] = mapped_column(
        ForeignKey("filament_spools.id"), nullable=True, index=True
    )
    formula_version: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    evidence_source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    snapshot_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    printer_model: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    inputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    outputs_json: Mapped[str] = mapped_column(Text, nullable=False)

    product = relationship("Product", back_populates="cost_snapshots")
    filament_spool = relationship("FilamentSpool")
