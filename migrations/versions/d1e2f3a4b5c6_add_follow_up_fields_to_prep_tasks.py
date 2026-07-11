"""Add follow-up fields to prep_tasks

Revision ID: d1e2f3a4b5c6
Revises: c7c8d9e0f1a2
Create Date: 2025-07-11 15:30:00.000000

"""

from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c7c8d9e0f1a2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("prep_tasks", sa.Column("follow_up_type", sa.String(40), nullable=True, index=True))
    op.add_column("prep_tasks", sa.Column("customer_id", sa.Integer(), nullable=True))
    op.add_column("prep_tasks", sa.Column("related_order_id", sa.Integer(), nullable=True))
    op.add_column("prep_tasks", sa.Column("related_custom_request_id", sa.Integer(), nullable=True))
    op.add_column("prep_tasks", sa.Column("related_pos_sale_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_prep_tasks_customer_id", "prep_tasks", "customers", ["customer_id"], ["id"])
    op.create_foreign_key("fk_prep_tasks_related_order_id", "prep_tasks", "orders", ["related_order_id"], ["id"])
    op.create_foreign_key(
        "fk_prep_tasks_related_custom_request_id", "prep_tasks", "custom_requests",
        ["related_custom_request_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_prep_tasks_related_pos_sale_id", "prep_tasks", "pos_sales",
        ["related_pos_sale_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_prep_tasks_related_pos_sale_id", "prep_tasks", type_="foreignkey")
    op.drop_constraint("fk_prep_tasks_related_custom_request_id", "prep_tasks", type_="foreignkey")
    op.drop_constraint("fk_prep_tasks_related_order_id", "prep_tasks", type_="foreignkey")
    op.drop_constraint("fk_prep_tasks_customer_id", "prep_tasks", type_="foreignkey")
    op.drop_column("prep_tasks", "related_pos_sale_id")
    op.drop_column("prep_tasks", "related_custom_request_id")
    op.drop_column("prep_tasks", "related_order_id")
    op.drop_column("prep_tasks", "customer_id")
    op.drop_column("prep_tasks", "follow_up_type")
