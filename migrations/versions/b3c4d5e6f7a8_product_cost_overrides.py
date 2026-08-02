"""product cost-engine override columns (Issue 14 / Issue 38)

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-29 00:00:00.000000

Adds nullable per-product overrides for the cost engine so the Product Studio
can supply cost inputs the global settings do not cover:
packaging_cost_override, target_margin_percent_override,
market_allocation_override, payment_fee_rate_override, and
material_spool_override (a FK to filament_spools.id).
"""

from alembic import op
import sqlalchemy as sa


revision = "b3c4d5e6f7a8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "products", sa.Column("packaging_cost_override", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "products", sa.Column("target_margin_percent_override", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "products", sa.Column("market_allocation_override", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "products", sa.Column("payment_fee_rate_override", sa.Numeric(10, 4), nullable=True)
    )
    op.add_column(
        "products",
        sa.Column("material_spool_override", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_products_material_spool_override_filament_spools",
        "products",
        "filament_spools",
        ["material_spool_override"],
        ["id"],
    )


def downgrade():
    op.drop_constraint(
        "fk_products_material_spool_override_filament_spools",
        "products",
        type_="foreignkey",
    )
    op.drop_column("products", "material_spool_override")
    op.drop_column("products", "payment_fee_rate_override")
    op.drop_column("products", "market_allocation_override")
    op.drop_column("products", "target_margin_percent_override")
    op.drop_column("products", "packaging_cost_override")
