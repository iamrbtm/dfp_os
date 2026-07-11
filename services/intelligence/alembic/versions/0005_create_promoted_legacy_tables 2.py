"""create promoted legacy tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promoted_legacy_tables",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("review_state_id", sa.String(length=36), nullable=True),
        sa.Column("target_entity_type", sa.String(length=40), nullable=False),
        sa.Column("column_names", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("normalized_data", sa.JSON(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_batch_id", "table_name", name="uq_promoted_legacy_table_batch_table"),
    )
    op.create_index("ix_promoted_legacy_tables_table_name", "promoted_legacy_tables", ["table_name"])
    op.create_index("ix_promoted_legacy_tables_import_batch_id", "promoted_legacy_tables", ["import_batch_id"])
    op.create_index("ix_promoted_legacy_tables_review_state_id", "promoted_legacy_tables", ["review_state_id"])
    op.create_index("ix_promoted_legacy_tables_target_entity_type", "promoted_legacy_tables", ["target_entity_type"])


def downgrade() -> None:
    op.drop_table("promoted_legacy_tables")
