"""create normalized pipeline tables

Revision ID: 0007
Revises: fb3ad5aa0f7e
Create Date: 2026-07-03 06:45:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "fb3ad5aa0f7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="running", index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entity_counts", postgresql.JSON, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "normalized_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(36), nullable=True, index=True),
        sa.Column("promoted_table_id", sa.String(36), nullable=True, index=True),
        sa.Column("entity_type", sa.String(40), nullable=False, index=True),
        sa.Column("original_table_name", sa.String(255), nullable=False, index=True),
        sa.Column("original_primary_key", sa.String(512), nullable=True),
        sa.Column("name", sa.String(255), nullable=True, index=True),
        sa.Column("sku", sa.String(255), nullable=True, index=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("price_cents", sa.Integer, nullable=True),
        sa.Column("quantity", sa.Integer, nullable=True),
        sa.Column("amount_cents", sa.Integer, nullable=True),
        sa.Column("date_value", sa.Date, nullable=True, index=True),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("vendor_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(40), nullable=True),
        sa.Column("source_json", postgresql.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("normalized_entities")
    op.drop_table("pipeline_runs")
