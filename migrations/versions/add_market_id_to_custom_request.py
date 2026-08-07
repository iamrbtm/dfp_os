"""Add market_id to CustomRequest (Issue: follow-up generation)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "custom_requests",
        sa.Column("market_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_custom_requests_market_id", "custom_requests", ["market_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_custom_requests_market_id_markets"),
        source_table="custom_requests",
        referent_table="markets",
        local_cols=["market_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        op.f("fk_custom_requests_market_id_markets"),
        "custom_requests",
        type_="foreignkey",
    )
    op.drop_index("ix_custom_requests_market_id", table_name="custom_requests")
    op.drop_column("custom_requests", "market_id")
