"""Add Product Studio operations models

Revision ID: f6b7c8d9e0f1
Revises: f4a5b6c7d8e9
Create Date: 2026-07-14 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f6b7c8d9e0f1"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("story_what_it_is", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("story_who_it_is_for", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("story_materials", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("story_customization_options", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("story_internal_compliance_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("launch_override_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("retirement_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("block_reprint", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.create_table(
        "product_launch_checklist_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "key", name="uq_product_launch_checklist_product_key"),
    )
    op.create_index("ix_product_launch_checklist_items_product_id", "product_launch_checklist_items", ["product_id"])
    op.create_index("ix_product_launch_checklist_items_key", "product_launch_checklist_items", ["key"])
    op.create_index("ix_product_launch_checklist_items_completed", "product_launch_checklist_items", ["completed"])

    op.create_table(
        "product_photo_shots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("shot_type", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("image_reference", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "shot_type", name="uq_product_photo_shots_product_type"),
    )
    op.create_index("ix_product_photo_shots_product_id", "product_photo_shots", ["product_id"])
    op.create_index("ix_product_photo_shots_shot_type", "product_photo_shots", ["shot_type"])
    op.create_index("ix_product_photo_shots_completed", "product_photo_shots", ["completed"])

    op.create_table(
        "dead_stock_recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("suggested_action", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("action_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dead_stock_recommendations_product_id", "dead_stock_recommendations", ["product_id"])
    op.create_index("ix_dead_stock_recommendations_score", "dead_stock_recommendations", ["score"])
    op.create_index("ix_dead_stock_recommendations_status", "dead_stock_recommendations", ["status"])


def downgrade() -> None:
    op.drop_table("dead_stock_recommendations")
    op.drop_table("product_photo_shots")
    op.drop_table("product_launch_checklist_items")
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("block_reprint")
        batch_op.drop_column("retirement_reason")
        batch_op.drop_column("retired_at")
        batch_op.drop_column("launch_override_reason")
        batch_op.drop_column("story_internal_compliance_notes")
        batch_op.drop_column("story_customization_options")
        batch_op.drop_column("story_materials")
        batch_op.drop_column("story_who_it_is_for")
        batch_op.drop_column("story_what_it_is")
