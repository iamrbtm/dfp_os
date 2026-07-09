"""add missing intelligence models (clean rebuild for dev)

Revision ID: fb3ad5aa0f7e
Revises: 0005
Create Date: 2026-07-03 06:12:54.094592
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "fb3ad5aa0f7e"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop tables that need schema rebuild to avoid complex ALTER conflicts
    # Safe in dev — no production data
    op.execute("DROP TABLE IF EXISTS legacy_mariadb_table_snapshots CASCADE")
    op.execute("DROP TABLE IF EXISTS square_item_raw CASCADE")
    op.execute("DROP TABLE IF EXISTS sales_fact_lines CASCADE")
    op.execute("DROP TABLE IF EXISTS product_sales_summaries CASCADE")
    op.execute("DROP TABLE IF EXISTS seasonal_product_performance CASCADE")
    op.execute("DROP TABLE IF EXISTS channel_performance_summaries CASCADE")
    op.execute("DROP TABLE IF EXISTS historical_alias_mappings CASCADE")
    op.execute("DROP TABLE IF EXISTS warehouse_builds CASCADE")
    op.execute("DROP TABLE IF EXISTS knowledge_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS knowledge_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS decision_outcomes CASCADE")
    op.execute("DROP TABLE IF EXISTS ask_dfp_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS market_advisor_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS market_advisor_recommendations CASCADE")

    # legacy_table_manifests — drop and recreate to match new schema
    op.execute("DROP TABLE IF EXISTS legacy_table_manifests CASCADE")
    op.create_table(
        "legacy_table_manifests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_batch_id", sa.String(36), nullable=False, index=True),
        sa.Column("table_name", sa.String(255), nullable=False, index=True),
        sa.Column("estimated_row_count", sa.Integer, nullable=True),
        sa.Column("actual_row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("columns", postgresql.JSON, nullable=False),
        sa.Column("primary_key_columns", postgresql.JSON, nullable=True),
        sa.Column("import_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "legacy_mariadb_table_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_batch_id", sa.String(36), nullable=False, index=True),
        sa.Column("table_name", sa.String(255), nullable=False, index=True),
        sa.Column("estimated_rows", sa.Integer, nullable=True),
        sa.Column("columns", postgresql.JSON, nullable=False),
        sa.Column("primary_key_columns", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "square_item_raw",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_batch_id", sa.String(36), nullable=False, index=True),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("source_row_hash", sa.String(64), nullable=False, index=True),
        sa.Column("date", sa.String(20), nullable=True),
        sa.Column("time", sa.String(20), nullable=True),
        sa.Column("time_zone", sa.String(60), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("item", sa.String(255), nullable=True),
        sa.Column("qty", sa.String(40), nullable=True),
        sa.Column("price_point_name", sa.String(255), nullable=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("modifiers_applied", sa.String(255), nullable=True),
        sa.Column("gross_sales_cents", sa.Integer, nullable=True),
        sa.Column("discounts_cents", sa.Integer, nullable=True),
        sa.Column("net_sales_cents", sa.Integer, nullable=True),
        sa.Column("tax_cents", sa.Integer, nullable=True),
        sa.Column("transaction_id", sa.String(255), nullable=True, index=True),
        sa.Column("payment_id", sa.String(255), nullable=True),
        sa.Column("device_name", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("details_url", sa.String(512), nullable=True),
        sa.Column("event_type", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("dining_option", sa.String(255), nullable=True),
        sa.Column("customer_id", sa.String(255), nullable=True),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("customer_reference_id", sa.String(255), nullable=True),
        sa.Column("unit", sa.String(40), nullable=True),
        sa.Column("count", sa.String(40), nullable=True),
        sa.Column("gtin", sa.String(80), nullable=True),
        sa.Column("itemization_type", sa.String(80), nullable=True),
        sa.Column("fulfillment_note", sa.Text, nullable=True),
        sa.Column("channel", sa.String(255), nullable=True, index=True),
        sa.Column("card_brand", sa.String(80), nullable=True),
        sa.Column("sensitive_fields_present", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("raw_payload", postgresql.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "sales_fact_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(40), nullable=False, index=True),
        sa.Column("source_row_id", sa.String(36), nullable=True),
        sa.Column("sale_date", sa.Date, nullable=True),
        sa.Column("sale_year", sa.Integer, nullable=True, index=True),
        sa.Column("sale_month", sa.Integer, nullable=True, index=True),
        sa.Column("product_key", sa.String(255), nullable=False, index=True),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("variant_key", sa.String(255), nullable=True),
        sa.Column("category_name", sa.String(255), nullable=True, index=True),
        sa.Column("channel_name", sa.String(255), nullable=False, index=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("transaction_id", sa.String(255), nullable=True, index=True),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("gross_sales_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("discount_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("net_sales_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("evidence", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "product_sales_summaries",
        sa.Column("product_key", sa.String(255), primary_key=True),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("category_name", sa.String(255), nullable=True),
        sa.Column("total_units", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("total_net_sales_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("transaction_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active_months", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_units_per_active_month", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("avg_net_sales_cents_per_unit", sa.Integer, nullable=False, server_default="0"),
        sa.Column("first_sale_date", sa.Date, nullable=True),
        sa.Column("last_sale_date", sa.Date, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "seasonal_product_performance",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_key", sa.String(255), nullable=False, index=True),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("sale_month", sa.Integer, nullable=False, index=True),
        sa.Column("total_units", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("total_net_sales_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("transaction_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("product_key", "sale_month", name="uq_seasonal_product_key_month"),
    )

    op.create_table(
        "channel_performance_summaries",
        sa.Column("channel_name", sa.String(255), primary_key=True),
        sa.Column("total_units", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("total_net_sales_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("transaction_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active_months", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "historical_alias_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(40), nullable=False, index=True),
        sa.Column("entity_type", sa.String(40), nullable=False, index=True),
        sa.Column("source_value", sa.String(255), nullable=False),
        sa.Column("normalized_value", sa.String(255), nullable=False, index=True),
        sa.Column("target_entity_type", sa.String(40), nullable=True),
        sa.Column("target_entity_id", sa.String(255), nullable=True),
        sa.Column("target_display_name", sa.String(255), nullable=True),
        sa.Column("match_confidence", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("reviewed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("reviewed_by", sa.String(120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "warehouse_builds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(40), nullable=False, index=True),
        sa.Column("status", sa.String(40), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fact_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("product_summary_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("seasonal_summary_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("channel_summary_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSON, nullable=True),
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(80), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False, index=True),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("document_metadata", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("token_set", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_doc_index"),
    )

    op.create_table(
        "decision_outcomes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recommendation_id", sa.String(36), nullable=True, index=True),
        sa.Column("run_id", sa.String(36), nullable=True, index=True),
        sa.Column("decision_type", sa.String(80), nullable=False, server_default="market_advisor", index=True),
        sa.Column("user_action", sa.String(80), nullable=False),
        sa.Column("outcome_status", sa.String(80), nullable=False),
        sa.Column("actual_units", sa.Integer, nullable=True),
        sa.Column("actual_revenue_cents", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "ask_dfp_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("allowed_tools", postgresql.JSON, nullable=False),
        sa.Column("evidence", postgresql.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "market_advisor_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("market_name", sa.String(255), nullable=False),
        sa.Column("market_date", sa.Date, nullable=True),
        sa.Column("event_type", sa.String(120), nullable=True),
        sa.Column("max_products", sa.Integer, nullable=False, server_default="12"),
        sa.Column("input_context", postgresql.JSON, nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="completed", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "market_advisor_recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False, index=True),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("product_key", sa.String(255), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("category_name", sa.String(255), nullable=True),
        sa.Column("suggested_quantity", sa.Integer, nullable=False),
        sa.Column("suggested_print_quantity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expected_revenue_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(40), nullable=False),
        sa.Column("score", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("evidence", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS market_advisor_recommendations CASCADE")
    op.execute("DROP TABLE IF EXISTS market_advisor_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS ask_dfp_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS decision_outcomes CASCADE")
    op.execute("DROP TABLE IF EXISTS knowledge_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS knowledge_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS warehouse_builds CASCADE")
    op.execute("DROP TABLE IF EXISTS historical_alias_mappings CASCADE")
    op.execute("DROP TABLE IF EXISTS channel_performance_summaries CASCADE")
    op.execute("DROP TABLE IF EXISTS seasonal_product_performance CASCADE")
    op.execute("DROP TABLE IF EXISTS product_sales_summaries CASCADE")
    op.execute("DROP TABLE IF EXISTS sales_fact_lines CASCADE")
    op.execute("DROP TABLE IF EXISTS square_item_raw CASCADE")
    op.execute("DROP TABLE IF EXISTS legacy_mariadb_table_snapshots CASCADE")
    op.execute("DROP TABLE IF EXISTS legacy_table_manifests CASCADE")
