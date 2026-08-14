"""initial trend scout tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-13 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trend_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("keyword_or_category", sa.String(length=255), nullable=False),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("raw_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("business_id", sa.BigInteger(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_trend_snapshots_source_scraped",
        "trend_snapshots",
        ["source", "scraped_at"],
    )
    op.create_index(
        "ix_trend_snapshots_keyword_source",
        "trend_snapshots",
        ["keyword_or_category", "source"],
    )
    op.create_index(
        "ix_trend_snapshots_business_id",
        "trend_snapshots",
        ["business_id"],
    )

    op.create_table(
        "trend_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("report_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("top_opportunities", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("growing_categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("declining_categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("scoring_version", sa.String(length=64), nullable=False, server_default="v1"),
        sa.Column("business_id", sa.BigInteger(), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("pipeline_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.create_index("ix_trend_reports_report_date", "trend_reports", ["report_date"])
    op.create_index("ix_trend_reports_business_id", "trend_reports", ["business_id"])
    op.create_index("ix_trend_reports_run_id", "trend_reports", ["run_id"])

    op.create_table(
        "trend_opportunity_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("trend_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("score_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("recommended_action", sa.String(length=64), nullable=False, server_default="watch"),
        sa.Column("velocity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("momentum", sa.Float(), nullable=False, server_default="0"),
        sa.Column("purchase_intent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("license_risk", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("local_relevance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("dismissed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("business_id", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("report_id", "keyword", "source", name="uq_trend_opp_report_keyword_source"),
    )
    op.create_index("ix_trend_opp_report", "trend_opportunity_scores", ["report_id"])
    op.create_index("ix_trend_opp_score", "trend_opportunity_scores", ["score"])
    op.create_index("ix_trend_opp_business_id", "trend_opportunity_scores", ["business_id"])

    op.create_table(
        "source_health_records",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("trend_reports.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("keyword", sa.String(length=255), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("throttled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("throttle_reason", sa.String(length=64), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("business_id", sa.BigInteger(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.create_index("ix_source_health_source", "source_health_records", ["source"])
    op.create_index("ix_source_health_report", "source_health_records", ["report_id"])
    op.create_index("ix_source_health_business_id", "source_health_records", ["business_id"])

    op.create_table(
        "trend_weights",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("group", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("business_id", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("key", name="uq_trend_weights_key"),
    )
    op.create_index("ix_trend_weights_business_id", "trend_weights", ["business_id"])


def downgrade() -> None:
    op.drop_index("ix_trend_weights_business_id", table_name="trend_weights")
    op.drop_table("trend_weights")

    op.drop_index("ix_source_health_business_id", table_name="source_health_records")
    op.drop_index("ix_source_health_report", table_name="source_health_records")
    op.drop_index("ix_source_health_source", table_name="source_health_records")
    op.drop_table("source_health_records")

    op.drop_index("ix_trend_opp_business_id", table_name="trend_opportunity_scores")
    op.drop_index("ix_trend_opp_score", table_name="trend_opportunity_scores")
    op.drop_index("ix_trend_opp_report", table_name="trend_opportunity_scores")
    op.drop_table("trend_opportunity_scores")

    op.drop_index("ix_trend_reports_run_id", table_name="trend_reports")
    op.drop_index("ix_trend_reports_business_id", table_name="trend_reports")
    op.drop_index("ix_trend_reports_report_date", table_name="trend_reports")
    op.drop_table("trend_reports")

    op.drop_index("ix_trend_snapshots_business_id", table_name="trend_snapshots")
    op.drop_index("ix_trend_snapshots_keyword_source", table_name="trend_snapshots")
    op.drop_index("ix_trend_snapshots_source_scraped", table_name="trend_snapshots")
    op.drop_table("trend_snapshots")
