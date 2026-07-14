"""Add promotion models (content_drafts, sign_assets)

Revision ID: e3f4a5b6c7d8
Revises: b5a6c7d8e9f0
Create Date: 2025-07-13 10:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e3f4a5b6c7d8"
down_revision = "b5a6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "content_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=60), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("media_reference", sa.String(length=500), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("custom_request_id", sa.Integer(), nullable=True),
        sa.Column("planned_publish_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"],),
        sa.ForeignKeyConstraint(["custom_request_id"], ["custom_requests.id"],),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"],),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"],),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"],),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_content_drafts_channel"), "content_drafts", ["channel"])
    op.create_index(op.f("ix_content_drafts_custom_request_id"), "content_drafts", ["custom_request_id"])
    op.create_index(op.f("ix_content_drafts_market_id"), "content_drafts", ["market_id"])
    op.create_index(op.f("ix_content_drafts_planned_publish_date"), "content_drafts", ["planned_publish_date"])
    op.create_index(op.f("ix_content_drafts_product_id"), "content_drafts", ["product_id"])
    op.create_index(op.f("ix_content_drafts_status"), "content_drafts", ["status"])
    op.create_index(op.f("ix_content_drafts_title"), "content_drafts", ["title"])

    op.create_table(
        "sign_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=300), nullable=True),
        sa.Column("price_display", sa.String(length=60), nullable=True),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("care_note", sa.Text(), nullable=True),
        sa.Column("qr_target_url", sa.String(length=500), nullable=True),
        sa.Column("generated_html", sa.Text(), nullable=True),
        sa.Column("preview_html", sa.Text(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("collection_id", sa.Integer(), nullable=True),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"],),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"],),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"],),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sign_assets_status"), "sign_assets", ["status"])
    op.create_index(op.f("ix_sign_assets_title"), "sign_assets", ["title"])
    op.create_index(op.f("ix_sign_assets_product_id"), "sign_assets", ["product_id"])
    op.create_index(op.f("ix_sign_assets_collection_id"), "sign_assets", ["collection_id"])
    op.create_index(op.f("ix_sign_assets_market_id"), "sign_assets", ["market_id"])


def downgrade():
    op.drop_table("sign_assets")
    op.drop_table("content_drafts")
