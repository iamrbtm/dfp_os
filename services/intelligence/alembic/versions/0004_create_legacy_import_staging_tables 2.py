"""create legacy import staging tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legacy_table_manifests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("estimated_row_count", sa.Integer(), nullable=True),
        sa.Column("actual_row_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("primary_key_columns", sa.JSON(), nullable=True),
        sa.Column("import_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_batch_id", "table_name", name="uq_legacy_table_manifest_batch_table"),
    )
    op.create_index("ix_legacy_table_manifests_import_batch_id", "legacy_table_manifests", ["import_batch_id"])
    op.create_index("ix_legacy_table_manifests_table_name", "legacy_table_manifests", ["table_name"])

    op.create_table(
        "legacy_import_row_stage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("table_manifest_id", sa.String(length=36), nullable=False),
        sa.Column("source_table_name", sa.String(length=255), nullable=False),
        sa.Column("source_primary_key_value", sa.String(length=512), nullable=True),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("column_names", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("import_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_batch_id", "source_table_name", "row_number",
            name="uq_legacy_row_stage_batch_table_row",
        ),
    )
    op.create_index("ix_legacy_import_row_stage_import_batch_id", "legacy_import_row_stage", ["import_batch_id"])
    op.create_index("ix_legacy_import_row_stage_table_manifest_id", "legacy_import_row_stage", ["table_manifest_id"])
    op.create_index("ix_legacy_import_row_stage_source_table_name", "legacy_import_row_stage", ["source_table_name"])
    op.create_index("ix_legacy_import_row_stage_source_row_hash", "legacy_import_row_stage", ["source_row_hash"])
    op.create_index(
        "ix_legacy_import_row_stage_source_primary_key_value",
        "legacy_import_row_stage",
        ["source_primary_key_value"],
    )

    op.create_table(
        "legacy_table_review_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("table_name", name="uq_legacy_table_review_state_table_name"),
    )
    op.create_index("ix_legacy_table_review_state_decision", "legacy_table_review_state", ["decision"])
    op.create_index("ix_legacy_table_review_state_table_name", "legacy_table_review_state", ["table_name"])


def downgrade() -> None:
    op.drop_table("legacy_table_review_state")
    op.drop_table("legacy_import_row_stage")
    op.drop_table("legacy_table_manifests")
