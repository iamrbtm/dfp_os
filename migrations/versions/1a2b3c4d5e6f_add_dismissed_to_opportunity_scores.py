"""add dismissed and dismissed_at to trend_opportunity_scores

Revision ID: 1a2b3c4d5e6f
Revises: 9d8e7f6c5b4a
Create Date: 2026-06-30 22:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "1a2b3c4d5e6f"
down_revision = "9d8e7f6c5b4a"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("trend_opportunity_scores") as batch_op:
        batch_op.add_column(sa.Column("dismissed", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_trend_opportunity_scores_dismissed", ["dismissed"])


def downgrade():
    with op.batch_alter_table("trend_opportunity_scores") as batch_op:
        batch_op.drop_index("ix_trend_opportunity_scores_dismissed")
        batch_op.drop_column("dismissed_at")
        batch_op.drop_column("dismissed")
