"""add notifications and trend_task_runs tables

Revision ID: 9d8e7f6c5b4a
Revises: a7b8c9d0e1f2
Create Date: 2026-06-30 21:37:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "9d8e7f6c5b4a"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True, index=True),
        sa.Column("notification_type", sa.String(80), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("related_entity_type", sa.String(80), nullable=True),
        sa.Column("related_entity_id", sa.String(80), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, default=False, index=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("link", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "trend_task_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True, index=True),
        sa.Column("status", sa.String(40), nullable=False, default="pending", index=True),
        sa.Column("trigger", sa.String(40), nullable=False, default="manual"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("total_steps", sa.Integer(), nullable=False, default=0),
        sa.Column("completed_steps", sa.Integer(), nullable=False, default=0),
        sa.Column("current_step", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("source_health_summary", sa.JSON(), nullable=True),
        sa.Column("report_id", sa.Integer(), nullable=True),
        sa.Column("result_meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("trend_task_runs")
    op.drop_table("notifications")
