"""add trend_scout tables

Revision ID: 787cadb6f437
Revises: e5f6a7b8c9d0
Create Date: 2026-06-27 23:13:25.380991

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '787cadb6f437'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('trend_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('report_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('top_opportunities', sa.JSON(), nullable=True),
        sa.Column('growing_categories', sa.JSON(), nullable=True),
        sa.Column('declining_trends', sa.JSON(), nullable=True),
        sa.Column('pipeline_meta', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trend_reports_report_date'), 'trend_reports', ['report_date'], unique=False)

    op.create_table('trend_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(length=80), nullable=False),
        sa.Column('keyword_or_category', sa.String(length=255), nullable=False),
        sa.Column('scraped_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trend_snapshots_source'), 'trend_snapshots', ['source'], unique=False)
    op.create_index(op.f('ix_trend_snapshots_keyword_or_category'), 'trend_snapshots', ['keyword_or_category'], unique=False)
    op.create_index(op.f('ix_trend_snapshots_scraped_at'), 'trend_snapshots', ['scraped_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_trend_snapshots_scraped_at'), table_name='trend_snapshots')
    op.drop_index(op.f('ix_trend_snapshots_keyword_or_category'), table_name='trend_snapshots')
    op.drop_index(op.f('ix_trend_snapshots_source'), table_name='trend_snapshots')
    op.drop_table('trend_snapshots')
    op.drop_index(op.f('ix_trend_reports_report_date'), table_name='trend_reports')
    op.drop_table('trend_reports')
