"""create intelligence phase 1-4 tables

Revision ID: 0001
Revises:
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_batches_source", "import_batches", ["source"])
    op.create_index("ix_import_batches_source_fingerprint", "import_batches", ["source_fingerprint"])
    op.create_index("ix_import_batches_status", "import_batches", ["status"])

    op.create_table(
        "square_item_raw",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=True),
        sa.Column("time", sa.String(length=20), nullable=True),
        sa.Column("time_zone", sa.String(length=80), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("item", sa.String(length=255), nullable=True),
        sa.Column("qty", sa.String(length=80), nullable=True),
        sa.Column("price_point_name", sa.String(length=255), nullable=True),
        sa.Column("sku", sa.String(length=120), nullable=True),
        sa.Column("modifiers_applied", sa.Text(), nullable=True),
        sa.Column("gross_sales_cents", sa.Integer(), nullable=True),
        sa.Column("discounts_cents", sa.Integer(), nullable=True),
        sa.Column("net_sales_cents", sa.Integer(), nullable=True),
        sa.Column("tax_cents", sa.Integer(), nullable=True),
        sa.Column("transaction_id", sa.String(length=120), nullable=True),
        sa.Column("payment_id", sa.String(length=120), nullable=True),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("details_url", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("dining_option", sa.String(length=120), nullable=True),
        sa.Column("customer_id", sa.String(length=120), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("customer_reference_id", sa.String(length=120), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("count", sa.String(length=80), nullable=True),
        sa.Column("gtin", sa.String(length=120), nullable=True),
        sa.Column("itemization_type", sa.String(length=120), nullable=True),
        sa.Column("fulfillment_note", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(length=255), nullable=True),
        sa.Column("card_brand", sa.String(length=80), nullable=True),
        sa.Column("sensitive_fields_present", sa.Boolean(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_batch_id", "row_number", name="uq_square_item_raw_batch_row"),
    )
    op.create_index("ix_square_item_raw_category", "square_item_raw", ["category"])
    op.create_index("ix_square_item_raw_channel", "square_item_raw", ["channel"])
    op.create_index("ix_square_item_raw_customer_id", "square_item_raw", ["customer_id"])
    op.create_index("ix_square_item_raw_date", "square_item_raw", ["date"])
    op.create_index("ix_square_item_raw_import_batch_id", "square_item_raw", ["import_batch_id"])
    op.create_index("ix_square_item_raw_item", "square_item_raw", ["item"])
    op.create_index("ix_square_item_raw_location", "square_item_raw", ["location"])
    op.create_index("ix_square_item_raw_payment_id", "square_item_raw", ["payment_id"])
    op.create_index("ix_square_item_raw_sku", "square_item_raw", ["sku"])
    op.create_index("ix_square_item_raw_source_row_hash", "square_item_raw", ["source_row_hash"])
    op.create_index("ix_square_item_raw_transaction_id", "square_item_raw", ["transaction_id"])

    op.create_table(
        "legacy_mariadb_table_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("estimated_rows", sa.Integer(), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("primary_key_columns", sa.JSON(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legacy_mariadb_table_snapshots_import_batch_id", "legacy_mariadb_table_snapshots", ["import_batch_id"])
    op.create_index("ix_legacy_mariadb_table_snapshots_table_name", "legacy_mariadb_table_snapshots", ["table_name"])

    op.create_table(
        "historical_alias_mappings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("source_value", sa.String(length=255), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=True),
        sa.Column("target_entity_type", sa.String(length=40), nullable=True),
        sa.Column("target_entity_id", sa.String(length=120), nullable=True),
        sa.Column("target_display_name", sa.String(length=255), nullable=True),
        sa.Column("match_confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "entity_type", "source_value", name="uq_historical_alias_source_value"),
    )
    op.create_index("ix_historical_alias_mappings_entity_type", "historical_alias_mappings", ["entity_type"])
    op.create_index("ix_historical_alias_mappings_normalized_value", "historical_alias_mappings", ["normalized_value"])
    op.create_index("ix_historical_alias_mappings_reviewed", "historical_alias_mappings", ["reviewed"])
    op.create_index("ix_historical_alias_mappings_source", "historical_alias_mappings", ["source"])
    op.create_index("ix_historical_alias_mappings_source_value", "historical_alias_mappings", ["source_value"])
    op.create_index("ix_historical_alias_mappings_target_entity_id", "historical_alias_mappings", ["target_entity_id"])


def downgrade() -> None:
    op.drop_table("historical_alias_mappings")
    op.drop_table("legacy_mariadb_table_snapshots")
    op.drop_table("square_item_raw")
    op.drop_table("import_batches")
