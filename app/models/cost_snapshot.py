from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class CostSnapshotConfidence(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CostSnapshotDensitySource(StrEnum):
    DEFAULT = "default"
    EMBEDDED = "embedded"
    MANUAL = "manual"


class CostSnapshot(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "cost_snapshots"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    filament_spool_id: Mapped[int | None] = mapped_column(
        ForeignKey("filament_spools.id"), nullable=True, index=True
    )
    model_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_model_assets.id"), nullable=True, index=True
    )
    analysis_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_analysis_runs.id"), nullable=True, index=True
    )
    formula_version: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    evidence_source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    snapshot_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    printer_model: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    slicer_settings_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    material: Mapped[str | None] = mapped_column(String(40), nullable=True)
    density: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    density_source: Mapped[CostSnapshotDensitySource | None] = mapped_column(
        Enum(CostSnapshotDensitySource, native_enum=False, length=20), nullable=True
    )
    scale_percent: Mapped[int | None] = mapped_column(nullable=True)
    copies: Mapped[int | None] = mapped_column(nullable=True)
    parsed_filament_grams: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    parsed_print_minutes: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    cost_resolver_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    inputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    outputs_json: Mapped[str] = mapped_column(Text, nullable=False)

    product = relationship("Product", back_populates="cost_snapshots")
    filament_spool = relationship("FilamentSpool")
    model_asset = relationship("ProductModelAsset")
    analysis_run = relationship("ProductAnalysisRun")

    __table_args__ = (Index("ix_cost_snapshots_product_stale", "product_id", "stale"),)
