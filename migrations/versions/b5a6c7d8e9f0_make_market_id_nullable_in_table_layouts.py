"""Make market_id nullable in market_table_layouts

Revision ID: b5a6c7d8e9f0
Revises: e2f3a4b5c6d7
Create Date: 2026-07-13 00:15:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b5a6c7d8e9f0"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column("market_table_layouts", "market_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("market_table_layouts", "market_id", existing_type=sa.Integer(), nullable=False)
