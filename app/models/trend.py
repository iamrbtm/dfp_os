from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class TrendSnapshot(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "trend_snapshots"

    source: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True
    )
    keyword_or_category: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    raw_metadata: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )


class TrendReport(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "trend_reports"

    report_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_opportunities: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    growing_categories: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    declining_trends: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    pipeline_meta: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )

    opportunity_scores = relationship(
        "TrendOpportunityScore", back_populates="report", cascade="all, delete-orphan"
    )
    source_health_records = relationship(
        "SourceHealthRecord", back_populates="report", cascade="all, delete-orphan"
    )


class TrendOpportunityScore(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "trend_opportunity_scores"

    report_id: Mapped[int] = mapped_column(
        ForeignKey("trend_reports.id"), nullable=False, index=True
    )
    candidate_type: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    keyword: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    opportunity_score: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_intent: Mapped[int] = mapped_column(Integer, nullable=False)
    trend_velocity: Mapped[int] = mapped_column(Integer, nullable=False)
    price_resilience: Mapped[int] = mapped_column(Integer, nullable=False)
    low_saturation: Mapped[int] = mapped_column(Integer, nullable=False)
    local_fit: Mapped[int] = mapped_column(Integer, nullable=False)
    production_fit: Mapped[int] = mapped_column(Integer, nullable=False)
    license_risk: Mapped[int] = mapped_column(Integer, nullable=False)

    action: Mapped[str] = mapped_column(String(40), nullable=False)
    inventory_available: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    license_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    score_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_health: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    match_confidence: Mapped[str | None] = mapped_column(String(40), nullable=True)

    report = relationship("TrendReport", back_populates="opportunity_scores")


class SourceHealthRecord(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "source_health_records"

    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("trend_reports.id"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    keyword: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    report = relationship("TrendReport", back_populates="source_health_records")
