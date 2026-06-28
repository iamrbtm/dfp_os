"""Add product studio analysis and conversion fields

Revision ID: 7d91b5f3e6c2
Revises: 4a6a5e4c2d11
Create Date: 2026-06-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "7d91b5f3e6c2"
down_revision = "4a6a5e4c2d11"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("analysis_status", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("analysis_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("analysis_requested_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("analysis_completed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("parsed_volume_mm3", sa.Numeric(12, 4), nullable=True))
        batch_op.add_column(sa.Column("parsed_surface_area_mm2", sa.Numeric(12, 4), nullable=True))
        batch_op.add_column(sa.Column("parsed_triangle_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("parsed_filament_grams", sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column("parsed_print_minutes", sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column("parsed_material_cost", sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column("convert_status", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("conversion_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("converted_model_path", sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_column("converted_model_path")
        batch_op.drop_column("conversion_error")
        batch_op.drop_column("convert_status")
        batch_op.drop_column("parsed_material_cost")
        batch_op.drop_column("parsed_print_minutes")
        batch_op.drop_column("parsed_filament_grams")
        batch_op.drop_column("parsed_triangle_count")
        batch_op.drop_column("parsed_surface_area_mm2")
        batch_op.drop_column("parsed_volume_mm3")
        batch_op.drop_column("analysis_completed_at")
        batch_op.drop_column("analysis_requested_at")
        batch_op.drop_column("analysis_error")
        batch_op.drop_column("analysis_status")
