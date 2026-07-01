"""add internal demand events

Revision ID: f5b1d2c3a4e6
Revises: 43c4bd2dd978
Create Date: 2026-06-29 09:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "f5b1d2c3a4e6"
down_revision = "43c4bd2dd978"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "internal_demand_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("collection_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("custom_request_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("value", sa.Numeric(10, 2), nullable=True),
        sa.Column("session_key", sa.String(length=80), nullable=True),
        sa.Column("text_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("extracted_terms", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"]),
        sa.ForeignKeyConstraint(["custom_request_id"], ["custom_requests.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_internal_demand_events_category_id"),
        "internal_demand_events",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_collection_id"),
        "internal_demand_events",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_custom_request_id"),
        "internal_demand_events",
        ["custom_request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_event_type"),
        "internal_demand_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_keyword"),
        "internal_demand_events",
        ["keyword"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_occurred_at"),
        "internal_demand_events",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_order_id"),
        "internal_demand_events",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_product_id"),
        "internal_demand_events",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_session_key"),
        "internal_demand_events",
        ["session_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_source"),
        "internal_demand_events",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_internal_demand_events_text_fingerprint"),
        "internal_demand_events",
        ["text_fingerprint"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_internal_demand_events_text_fingerprint"), table_name="internal_demand_events"
    )
    op.drop_index(op.f("ix_internal_demand_events_source"), table_name="internal_demand_events")
    op.drop_index(
        op.f("ix_internal_demand_events_session_key"), table_name="internal_demand_events"
    )
    op.drop_index(op.f("ix_internal_demand_events_product_id"), table_name="internal_demand_events")
    op.drop_index(op.f("ix_internal_demand_events_order_id"), table_name="internal_demand_events")
    op.drop_index(
        op.f("ix_internal_demand_events_occurred_at"), table_name="internal_demand_events"
    )
    op.drop_index(op.f("ix_internal_demand_events_keyword"), table_name="internal_demand_events")
    op.drop_index(op.f("ix_internal_demand_events_event_type"), table_name="internal_demand_events")
    op.drop_index(
        op.f("ix_internal_demand_events_custom_request_id"), table_name="internal_demand_events"
    )
    op.drop_index(
        op.f("ix_internal_demand_events_collection_id"), table_name="internal_demand_events"
    )
    op.drop_index(
        op.f("ix_internal_demand_events_category_id"), table_name="internal_demand_events"
    )
    op.drop_table("internal_demand_events")
