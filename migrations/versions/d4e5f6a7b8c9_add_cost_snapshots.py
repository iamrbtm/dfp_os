"""Add cost_snapshots table

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-06-25 11:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cost_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("filament_spool_id", sa.Integer(), sa.ForeignKey("filament_spools.id"), nullable=True),
        sa.Column("formula_version", sa.String(length=40), nullable=False),
        sa.Column("evidence_source", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("snapshot_reason", sa.String(length=80), nullable=True),
        sa.Column("printer_model", sa.String(length=160), nullable=True),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("inputs_json", sa.Text(), nullable=False),
        sa.Column("outputs_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_cost_snapshots_product_id", "cost_snapshots", ["product_id"])
    op.create_index("ix_cost_snapshots_filament_spool_id", "cost_snapshots", ["filament_spool_id"])
    op.create_index("ix_cost_snapshots_formula_version", "cost_snapshots", ["formula_version"])
    op.create_index("ix_cost_snapshots_evidence_source", "cost_snapshots", ["evidence_source"])
    op.create_index("ix_cost_snapshots_confidence", "cost_snapshots", ["confidence"])
    op.create_index("ix_cost_snapshots_printer_model", "cost_snapshots", ["printer_model"])
    op.create_index("ix_cost_snapshots_stale", "cost_snapshots", ["stale"])


def downgrade():
    op.drop_index("ix_cost_snapshots_stale", table_name="cost_snapshots")
    op.drop_index("ix_cost_snapshots_printer_model", table_name="cost_snapshots")
    op.drop_index("ix_cost_snapshots_confidence", table_name="cost_snapshots")
    op.drop_index("ix_cost_snapshots_evidence_source", table_name="cost_snapshots")
    op.drop_index("ix_cost_snapshots_formula_version", table_name="cost_snapshots")
    op.drop_index("ix_cost_snapshots_filament_spool_id", table_name="cost_snapshots")
    op.drop_index("ix_cost_snapshots_product_id", table_name="cost_snapshots")
    op.drop_table("cost_snapshots")
