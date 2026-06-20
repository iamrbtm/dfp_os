"""Add zip code to markets

Revision ID: 3b7c2f4e9a10
Revises: 2f9a1b7c4d8e
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "3b7c2f4e9a10"
down_revision = "2f9a1b7c4d8e"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("markets") as batch_op:
        batch_op.add_column(sa.Column("zip_code", sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table("markets") as batch_op:
        batch_op.drop_column("zip_code")
