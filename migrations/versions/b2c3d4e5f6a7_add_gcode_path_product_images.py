"""Add gcode_path to model_assets, product_images table, pos_image_path

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "model_assets",
        sa.Column("gcode_path", sa.String(500), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("pos_image_path", sa.String(255), nullable=True),
    )
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("variant_id", sa.Integer(), sa.ForeignKey("product_variants.id"), nullable=True, index=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("is_default", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_pos", sa.Boolean(), default=False, nullable=False),
        sa.Column("sort_order", sa.Integer(), default=0, nullable=False),
        sa.Column("alt_text", sa.String(255), nullable=True),
    )


def downgrade():
    op.drop_table("product_images")
    op.drop_column("products", "pos_image_path")
    op.drop_column("model_assets", "gcode_path")
