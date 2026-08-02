"""product collection memberships

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-02 00:00:00.000000

Adds a many-to-many collection membership table while preserving
products.collection_id as the primary collection for older reports and API
consumers.
"""

from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_collections",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "collection_id"),
    )
    op.create_index("ix_product_collections_product_id", "product_collections", ["product_id"])
    op.create_index(
        "ix_product_collections_collection_id", "product_collections", ["collection_id"]
    )
    op.execute(
        """
        INSERT INTO product_collections (product_id, collection_id)
        SELECT id, collection_id
        FROM products
        WHERE collection_id IS NOT NULL
        """
    )


def downgrade():
    op.drop_index("ix_product_collections_collection_id", table_name="product_collections")
    op.drop_index("ix_product_collections_product_id", table_name="product_collections")
    op.drop_table("product_collections")
