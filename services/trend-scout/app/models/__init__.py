from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PrimaryKeyMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TrendSnapshot(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trend_snapshots"
    __table_args__ = (
        Index("ix_trend_snapshots_source_scraped", "source", "scraped_at"),
        Index("ix_trend_snapshots_keyword_source", "keyword_or_category", "source"),
    )

    source: Mapped[str] = mapped_column(String(64), nullable=False)
    keyword_or_category: Mapped[str] = mapped_column(String(255), nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    raw_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    business_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TrendReport(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trend_reports"
    __table_args__ = (Index("ix_trend_reports_report_date", "report_date"),)

    report_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    top_opportunities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    growing_categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    declining_categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    scoring_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    business_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    pipeline_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    opportunity_scores: Mapped[list["TrendOpportunityScore"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
    )
    source_health_records: Mapped[list["SourceHealthRecord"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
    )


class TrendOpportunityScore(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trend_opportunity_scores"
    __table_args__ = (
        UniqueConstraint("report_id", "keyword", "source", name="uq_trend_opp_report_keyword_source"),
        Index("ix_trend_opp_report", "report_id"),
        Index("ix_trend_opp_score", "score"),
    )

    report_id: Mapped[int] = mapped_column(ForeignKey("trend_reports.id", ondelete="CASCADE"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    recommended_action: Mapped[str] = mapped_column(String(64), nullable=False, default="watch")
    velocity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    momentum: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    purchase_intent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    license_risk: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    local_relevance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dismissed: Mapped[bool] = mapped_column(nullable=False, default=False)
    business_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    report: Mapped[TrendReport] = relationship(back_populates="opportunity_scores")


class SourceHealthRecord(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_health_records"
    __table_args__ = (
        Index("ix_source_health_source", "source"),
        Index("ix_source_health_report", "report_id"),
    )

    report_id: Mapped[int | None] = mapped_column(ForeignKey("trend_reports.id", ondelete="CASCADE"), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    keyword: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    throttled: Mapped[bool] = mapped_column(nullable=False, default=False)
    throttle_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    business_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    report: Mapped[TrendReport | None] = relationship(back_populates="source_health_records")


class TrendWeight(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trend_weights"
    __table_args__ = (UniqueConstraint("key", name="uq_trend_weights_key"),)

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    group: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    business_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
