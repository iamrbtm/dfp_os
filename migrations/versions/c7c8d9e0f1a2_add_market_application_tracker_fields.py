"""add market application tracker fields

Revision ID: c7c8d9e0f1a2
Revises: b304dc2ba9cb
Create Date: 2026-07-11 09:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "c7c8d9e0f1a2"
down_revision = "b304dc2ba9cb"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("markets", schema=None) as batch_op:
        batch_op.add_column(sa.Column("application_deadline", sa.Date(), nullable=True, index=True))
        batch_op.add_column(sa.Column("application_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("application_contact", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("booth_rules", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("required_documents", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("follow_up_date", sa.Date(), nullable=True, index=True))
        batch_op.add_column(sa.Column("worth_repeating", sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table("markets", schema=None) as batch_op:
        batch_op.drop_column("worth_repeating")
        batch_op.drop_column("follow_up_date")
        batch_op.drop_column("required_documents")
        batch_op.drop_column("booth_rules")
        batch_op.drop_column("application_contact")
        batch_op.drop_column("application_url")
        batch_op.drop_column("application_deadline")
