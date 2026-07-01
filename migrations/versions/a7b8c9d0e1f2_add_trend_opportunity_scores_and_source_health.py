"""add trend_opportunity_scores and source_health_records

Revision ID: a7b8c9d0e1f2
Revises: f5b1d2c3a4e6
Create Date: 2026-06-29 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f5b1d2c3a4e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trend_opportunity_scores",
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("candidate_type", sa.String(length=40), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("opportunity_score", sa.Integer(), nullable=False),
        sa.Column("purchase_intent", sa.Integer(), nullable=False),
        sa.Column("trend_velocity", sa.Integer(), nullable=False),
        sa.Column("price_resilience", sa.Integer(), nullable=False),
        sa.Column("low_saturation", sa.Integer(), nullable=False),
        sa.Column("local_fit", sa.Integer(), nullable=False),
        sa.Column("production_fit", sa.Integer(), nullable=False),
        sa.Column("license_risk", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("inventory_available", sa.Integer(), nullable=False),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("license_status", sa.String(length=40), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("source_health", sa.JSON(), nullable=True),
        sa.Column("match_confidence", sa.String(length=40), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["trend_reports.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_trend_opportunity_scores_candidate_type"),
        "trend_opportunity_scores",
        ["candidate_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trend_opportunity_scores_keyword"),
        "trend_opportunity_scores",
        ["keyword"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trend_opportunity_scores_product_id"),
        "trend_opportunity_scores",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trend_opportunity_scores_report_id"),
        "trend_opportunity_scores",
        ["report_id"],
        unique=False,
    )

    op.create_table(
        "source_health_records",
        sa.Column("report_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["trend_reports.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_source_health_records_report_id"),
        "source_health_records",
        ["report_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_source_health_records_source"),
        "source_health_records",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_source_health_records_status"),
        "source_health_records",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_source_health_records_status"), table_name="source_health_records"
    )
    op.drop_index(
        op.f("ix_source_health_records_source"), table_name="source_health_records"
    )
    op.drop_index(
        op.f("ix_source_health_records_report_id"), table_name="source_health_records"
    )
    op.drop_table("source_health_records")
    op.drop_index(
        op.f("ix_trend_opportunity_scores_report_id"),
        table_name="trend_opportunity_scores",
    )
    op.drop_index(
        op.f("ix_trend_opportunity_scores_product_id"),
        table_name="trend_opportunity_scores",
    )
    op.drop_index(
        op.f("ix_trend_opportunity_scores_keyword"),
        table_name="trend_opportunity_scores",
    )
    op.drop_index(
        op.f("ix_trend_opportunity_scores_candidate_type"),
        table_name="trend_opportunity_scores",
    )
    op.drop_table("trend_opportunity_scores")
