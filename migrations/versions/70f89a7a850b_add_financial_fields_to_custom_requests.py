"""Add financial fields to custom requests

Revision ID: 70f89a7a850b
Revises: 83911c79966b
Create Date: 2026-06-16 10:26:09.123904

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '70f89a7a850b'
down_revision = '83911c79966b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('custom_requests', sa.Column('subtotal', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('custom_requests', sa.Column('tax', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('custom_requests', sa.Column('discount', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('custom_requests', sa.Column('total', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('custom_requests', sa.Column('amount_paid', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade():
    op.drop_column('custom_requests', 'amount_paid')
    op.drop_column('custom_requests', 'total')
    op.drop_column('custom_requests', 'discount')
    op.drop_column('custom_requests', 'tax')
    op.drop_column('custom_requests', 'subtotal')
