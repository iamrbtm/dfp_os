"""create warehouse and market advisor tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_builds",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fact_rows", sa.Integer(), nullable=False),
        sa.Column("product_summary_rows", sa.Integer(), nullable=False),
        sa.Column("seasonal_summary_rows", sa.Integer(), nullable=False),
        sa.Column("channel_summary_rows", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_warehouse_builds_source", "warehouse_builds", ["source"])
    op.create_index("ix_warehouse_builds_status", "warehouse_builds", ["status"])

    op.create_table(
        "sales_fact_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("source_row_id", sa.String(length=36), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=True),
        sa.Column("sale_year", sa.Integer(), nullable=True),
        sa.Column("sale_month", sa.Integer(), nullable=True),
        sa.Column("product_key", sa.String(length=255), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("variant_key", sa.String(length=255), nullable=True),
        sa.Column("category_name", sa.String(length=255), nullable=True),
        sa.Column("channel_name", sa.String(length=255), nullable=True),
        sa.Column("sku", sa.String(length=120), nullable=True),
        sa.Column("transaction_id", sa.String(length=120), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("gross_sales_cents", sa.Integer(), nullable=False),
        sa.Column("discount_cents", sa.Integer(), nullable=False),
        sa.Column("net_sales_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_row_id", name="uq_sales_fact_source_row"),
    )
    for column in (
        "source",
        "source_row_id",
        "sale_date",
        "sale_year",
        "sale_month",
        "product_key",
        "product_name",
        "variant_key",
        "category_name",
        "channel_name",
        "sku",
        "transaction_id",
    ):
        op.create_index(f"ix_sales_fact_lines_{column}", "sales_fact_lines", [column])

    op.create_table(
        "product_sales_summaries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_key", sa.String(length=255), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("category_name", sa.String(length=255), nullable=True),
        sa.Column("total_units", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("total_net_sales_cents", sa.Integer(), nullable=False),
        sa.Column("transaction_count", sa.Integer(), nullable=False),
        sa.Column("active_months", sa.Integer(), nullable=False),
        sa.Column("avg_units_per_active_month", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("avg_net_sales_cents_per_unit", sa.Integer(), nullable=False),
        sa.Column("first_sale_date", sa.Date(), nullable=True),
        sa.Column("last_sale_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_key", name="uq_product_sales_summary_product_key"),
    )
    op.create_index("ix_product_sales_summaries_category_name", "product_sales_summaries", ["category_name"])
    op.create_index("ix_product_sales_summaries_last_sale_date", "product_sales_summaries", ["last_sale_date"])
    op.create_index("ix_product_sales_summaries_product_key", "product_sales_summaries", ["product_key"])
    op.create_index("ix_product_sales_summaries_product_name", "product_sales_summaries", ["product_name"])

    op.create_table(
        "seasonal_product_performance",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_key", sa.String(length=255), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("sale_month", sa.Integer(), nullable=False),
        sa.Column("total_units", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("total_net_sales_cents", sa.Integer(), nullable=False),
        sa.Column("transaction_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_key", "sale_month", name="uq_seasonal_product_month"),
    )
    op.create_index("ix_seasonal_product_performance_product_key", "seasonal_product_performance", ["product_key"])
    op.create_index("ix_seasonal_product_performance_product_name", "seasonal_product_performance", ["product_name"])
    op.create_index("ix_seasonal_product_performance_sale_month", "seasonal_product_performance", ["sale_month"])

    op.create_table(
        "channel_performance_summaries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("channel_name", sa.String(length=255), nullable=False),
        sa.Column("total_units", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("total_net_sales_cents", sa.Integer(), nullable=False),
        sa.Column("transaction_count", sa.Integer(), nullable=False),
        sa.Column("active_months", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_name", name="uq_channel_performance_channel"),
    )
    op.create_index("ix_channel_performance_summaries_channel_name", "channel_performance_summaries", ["channel_name"])

    op.create_table(
        "market_advisor_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("market_name", sa.String(length=255), nullable=False),
        sa.Column("market_date", sa.Date(), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=True),
        sa.Column("max_products", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("input_context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_advisor_runs_event_type", "market_advisor_runs", ["event_type"])
    op.create_index("ix_market_advisor_runs_market_date", "market_advisor_runs", ["market_date"])
    op.create_index("ix_market_advisor_runs_status", "market_advisor_runs", ["status"])

    op.create_table(
        "market_advisor_recommendations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("product_key", sa.String(length=255), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("category_name", sa.String(length=255), nullable=True),
        sa.Column("suggested_quantity", sa.Integer(), nullable=False),
        sa.Column("suggested_print_quantity", sa.Integer(), nullable=False),
        sa.Column("expected_revenue_cents", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=40), nullable=False),
        sa.Column("score", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "rank", name="uq_market_advisor_run_rank"),
    )
    op.create_index("ix_market_advisor_recommendations_product_key", "market_advisor_recommendations", ["product_key"])
    op.create_index("ix_market_advisor_recommendations_run_id", "market_advisor_recommendations", ["run_id"])


def downgrade() -> None:
    op.drop_table("market_advisor_recommendations")
    op.drop_table("market_advisor_runs")
    op.drop_table("channel_performance_summaries")
    op.drop_table("seasonal_product_performance")
    op.drop_table("product_sales_summaries")
    op.drop_table("sales_fact_lines")
    op.drop_table("warehouse_builds")
