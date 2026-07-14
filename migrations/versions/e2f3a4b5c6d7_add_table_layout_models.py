"""Add MarketTableLayout, MarketTableSection, MarketTablePlacement models

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2025-07-11 16:00:00.000000

"""

from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "market_table_layouts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("photo_path", sa.String(500), nullable=True),
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("copied_from_layout_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["copied_from_layout_id"], ["market_table_layouts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_table_layouts_market_id", "market_table_layouts", ["market_id"])
    op.create_index("ix_market_table_layouts_copied_from", "market_table_layouts", ["copied_from_layout_id"])

    op.create_table(
        "market_table_sections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("layout_id", sa.Integer(), nullable=False),
        sa.Column("section_type", sa.String(40), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["layout_id"], ["market_table_layouts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_table_sections_layout_id", "market_table_sections", ["layout_id"])
    op.create_index("ix_market_table_sections_section_type", "market_table_sections", ["section_type"])

    op.create_table(
        "market_table_placements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["section_id"], ["market_table_sections.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_table_placements_section_id", "market_table_placements", ["section_id"])
    op.create_index("ix_market_table_placements_product_id", "market_table_placements", ["product_id"])


def downgrade() -> None:
    op.drop_table("market_table_placements")
    op.drop_table("market_table_sections")
    op.drop_table("market_table_layouts")
