"""Remove market_tasks table, unify into prep_tasks

Revision ID: b304dc2ba9cb
Revises: 2b3c4d5e6f7a
Create Date: 2026-07-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "b304dc2ba9cb"
down_revision = "2b3c4d5e6f7a"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("market_tasks")


def downgrade():
    op.create_table(
        "market_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"],),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_market_tasks_market_id"), "market_tasks", ["market_id"])
    op.create_index(op.f("ix_market_tasks_task_type"), "market_tasks", ["task_type"])
    op.create_index(op.f("ix_market_tasks_status"), "market_tasks", ["status"])
    op.create_index(op.f("ix_market_tasks_due_at"), "market_tasks", ["due_at"])
    op.create_index(op.f("ix_market_tasks_completed_at"), "market_tasks", ["completed_at"])
