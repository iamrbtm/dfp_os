from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

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
