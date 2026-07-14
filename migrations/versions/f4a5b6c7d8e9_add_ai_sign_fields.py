"""Add layout and ai_image_path to sign_assets

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-14 04:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sign_assets", sa.Column("layout", sa.String(length=20), nullable=False, server_default="text"))
    op.add_column("sign_assets", sa.Column("ai_image_path", sa.String(length=500), nullable=True))
    op.create_index(op.f("ix_sign_assets_layout"), "sign_assets", ["layout"])


def downgrade():
    op.drop_index(op.f("ix_sign_assets_layout"), table_name="sign_assets")
    op.drop_column("sign_assets", "ai_image_path")
    op.drop_column("sign_assets", "layout")
