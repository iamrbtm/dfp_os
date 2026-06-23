"""Create audit_events table

Revision ID: 0001
Revises:
Create Date: 2026-06-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True, unique=True),
        sa.Column("tenant_id", sa.String(120), nullable=True, index=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(120), nullable=True, index=True),
        sa.Column("actor_type", sa.String(60), nullable=True),
        sa.Column("actor_display_name", sa.String(255), nullable=True),
        sa.Column("action", sa.String(120), nullable=False, index=True),
        sa.Column("entity_type", sa.String(120), nullable=False, index=True),
        sa.Column("entity_id", sa.String(120), nullable=True),
        sa.Column("source_service", sa.String(120), nullable=False, index=True),
        sa.Column("source_module", sa.String(120), nullable=True, index=True),
        sa.Column("request_id", sa.String(120), nullable=True, index=True),
        sa.Column("correlation_id", sa.String(120), nullable=True, index=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("before_state", JSONB, nullable=True),
        sa.Column("after_state", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=True),
    )

    op.create_index("ix_audit_events_entity_type_entity_id", "audit_events", ["entity_type", "entity_id"])
    op.create_index("ix_audit_events_idempotency_key", "audit_events", ["idempotency_key"], unique=True, postgresql_where=sa.text("idempotency_key IS NOT NULL"))


def downgrade() -> None:
    op.drop_table("audit_events")
