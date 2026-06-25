"""Add variant_id to model_assets for per-variant models

Revision ID: a1b2c3d4e5f6
Revises: 7d91b5f3e6c2
Create Date: 2026-06-24 04:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "7d91b5f3e6c2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "model_assets",
        sa.Column("variant_id", sa.Integer(), nullable=True, index=True),
    )
    op.create_foreign_key(
        "fk_model_assets_variant_id",
        "model_assets",
        "product_variants",
        ["variant_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_model_assets_variant_id", "model_assets", type_="foreignkey")
    op.drop_column("model_assets", "variant_id")
