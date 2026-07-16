"""Add print failure autopsy records

Revision ID: f6a7b8c9d0e1
Revises: f4a5b6c7d8e9
Create Date: 2026-07-14 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "print_failure_autopsies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("print_job_id", sa.Integer(), nullable=False),
        sa.Column("printer_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("filament_spool_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("model_asset_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("photo_reference", sa.String(length=500), nullable=True),
        sa.Column("corrective_action", sa.Text(), nullable=True),
        sa.Column("maintenance_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["filament_spool_id"], ["filament_spools.id"]),
        sa.ForeignKeyConstraint(["print_job_id"], ["print_jobs.id"]),
        sa.ForeignKeyConstraint(["printer_id"], ["printers.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_print_failure_autopsies_category", "print_failure_autopsies", ["category"])
    op.create_index("ix_print_failure_autopsies_filament_spool_id", "print_failure_autopsies", ["filament_spool_id"])
    op.create_index("ix_print_failure_autopsies_model_asset_id", "print_failure_autopsies", ["model_asset_id"])
    op.create_index("ix_print_failure_autopsies_print_job_id", "print_failure_autopsies", ["print_job_id"])
    op.create_index("ix_print_failure_autopsies_printer_id", "print_failure_autopsies", ["printer_id"])
    op.create_index("ix_print_failure_autopsies_product_id", "print_failure_autopsies", ["product_id"])
    op.create_index("ix_print_failure_autopsies_resolved", "print_failure_autopsies", ["resolved"])
    op.create_index("ix_print_failure_autopsies_severity", "print_failure_autopsies", ["severity"])
    op.create_index("ix_print_failure_autopsies_user_id", "print_failure_autopsies", ["user_id"])


def downgrade() -> None:
    op.drop_table("print_failure_autopsies")
