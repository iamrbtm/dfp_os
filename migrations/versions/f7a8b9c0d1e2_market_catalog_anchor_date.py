"""market catalog anchor date

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-10 12:00:00.000000

Adds an ``anchor_date`` column to ``market_catalog_listings`` so the
recurrence wizard can store a one-off market date (or DTSTART anchor) without
relying on the RRULE string.
"""

from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "market_catalog_listings",
        sa.Column("anchor_date", sa.Date(), nullable=True),
    )


def downgrade():
    op.drop_column("market_catalog_listings", "anchor_date")
