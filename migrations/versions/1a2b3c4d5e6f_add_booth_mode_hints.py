"""add booth mode hints

Revision ID: 1a2b3c4d5e6f
Revises: f4a5b6c7d8e9
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa


revision = "1a2b3c4d5e6f"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "booth_mode_hints",
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("pos_session_id", sa.Integer(), nullable=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["pos_session_id"], ["pos_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_booth_mode_hints_key", "booth_mode_hints", ["key"])
    op.create_index("ix_booth_mode_hints_market_id", "booth_mode_hints", ["market_id"])
    op.create_index("ix_booth_mode_hints_pos_session_id", "booth_mode_hints", ["pos_session_id"])
    op.create_index("ix_booth_mode_hints_status", "booth_mode_hints", ["status"])


def downgrade():
    op.drop_index("ix_booth_mode_hints_status", table_name="booth_mode_hints")
    op.drop_index("ix_booth_mode_hints_pos_session_id", table_name="booth_mode_hints")
    op.drop_index("ix_booth_mode_hints_market_id", table_name="booth_mode_hints")
    op.drop_index("ix_booth_mode_hints_key", table_name="booth_mode_hints")
    op.drop_table("booth_mode_hints")
