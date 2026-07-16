"""Add business_id to print_jobs

Revision ID: add_business_id_to_print_jobs
Revises: 2625ab9ebdbb
Create Date: 2026-07-14

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_business_id_to_print_jobs'
down_revision = '2625ab9ebdbb'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('print_jobs', sa.Column('business_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_print_jobs_business_id'), 'print_jobs', ['business_id'], unique=False)
    op.create_foreign_key(None, 'print_jobs', 'businesses', ['business_id'], ['id'])


def downgrade():
    op.drop_constraint(None, 'print_jobs', type_='foreignkey')
    op.drop_index(op.f('ix_print_jobs_business_id'), table_name='print_jobs')
    op.drop_column('print_jobs', 'business_id')