"""Add POS tables

Revision ID: b0a088770391
Revises: a32b5fb89ffc
Create Date: 2026-06-13 22:49:47.465292

"""

from alembic import op
import sqlalchemy as sa


revision = "b0a088770391"
down_revision = "a32b5fb89ffc"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pos_sessions",
        sa.Column("session_number", sa.String(length=40), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), nullable=False),
        sa.Column("closed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("inventory_location_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("OPEN", "CLOSED", "VOIDED", name="possessionstatus", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("opening_cash", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("closing_cash", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("expected_cash", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("cash_difference", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["inventory_location_id"], ["inventory_locations.id"]),
        sa.ForeignKeyConstraint(["opened_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pos_sessions_closed_by_user_id"), "pos_sessions", ["closed_by_user_id"], unique=False)
    op.create_index(op.f("ix_pos_sessions_inventory_location_id"), "pos_sessions", ["inventory_location_id"], unique=False)
    op.create_index(op.f("ix_pos_sessions_market_id"), "pos_sessions", ["market_id"], unique=False)
    op.create_index(op.f("ix_pos_sessions_opened_by_user_id"), "pos_sessions", ["opened_by_user_id"], unique=False)
    op.create_index(op.f("ix_pos_sessions_session_number"), "pos_sessions", ["session_number"], unique=True)
    op.create_index(op.f("ix_pos_sessions_status"), "pos_sessions", ["status"], unique=False)

    op.create_table(
        "pos_sales",
        sa.Column("pos_session_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("sale_number", sa.String(length=40), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("discount_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("tax_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("payment_method", sa.String(length=40), nullable=False),
        sa.Column("amount_received", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("change_due", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("COMPLETED", "VOIDED", "REFUNDED", name="possalestatus", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["pos_session_id"], ["pos_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pos_sales_customer_id"), "pos_sales", ["customer_id"], unique=False)
    op.create_index(op.f("ix_pos_sales_order_id"), "pos_sales", ["order_id"], unique=False)
    op.create_index(op.f("ix_pos_sales_payment_method"), "pos_sales", ["payment_method"], unique=False)
    op.create_index(op.f("ix_pos_sales_pos_session_id"), "pos_sales", ["pos_session_id"], unique=False)
    op.create_index(op.f("ix_pos_sales_sale_number"), "pos_sales", ["sale_number"], unique=True)

    op.create_table(
        "pos_sale_items",
        sa.Column("pos_sale_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "item_type",
            sa.Enum("PRODUCT", "CUSTOM_ITEM", "CUSTOM_DEPOSIT", "DISCOUNT", "FEE", name="possaleitemtype", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("custom_notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pos_sale_id"], ["pos_sales.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pos_sale_items_pos_sale_id"), "pos_sale_items", ["pos_sale_id"], unique=False)
    op.create_index(op.f("ix_pos_sale_items_product_id"), "pos_sale_items", ["product_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_pos_sale_items_product_id"), table_name="pos_sale_items")
    op.drop_index(op.f("ix_pos_sale_items_pos_sale_id"), table_name="pos_sale_items")
    op.drop_table("pos_sale_items")
    op.drop_index(op.f("ix_pos_sales_sale_number"), table_name="pos_sales")
    op.drop_index(op.f("ix_pos_sales_pos_session_id"), table_name="pos_sales")
    op.drop_index(op.f("ix_pos_sales_payment_method"), table_name="pos_sales")
    op.drop_index(op.f("ix_pos_sales_order_id"), table_name="pos_sales")
    op.drop_index(op.f("ix_pos_sales_customer_id"), table_name="pos_sales")
    op.drop_table("pos_sales")
    op.drop_index(op.f("ix_pos_sessions_status"), table_name="pos_sessions")
    op.drop_index(op.f("ix_pos_sessions_session_number"), table_name="pos_sessions")
    op.drop_index(op.f("ix_pos_sessions_opened_by_user_id"), table_name="pos_sessions")
    op.drop_index(op.f("ix_pos_sessions_market_id"), table_name="pos_sessions")
    op.drop_index(op.f("ix_pos_sessions_inventory_location_id"), table_name="pos_sessions")
    op.drop_index(op.f("ix_pos_sessions_closed_by_user_id"), table_name="pos_sessions")
    op.drop_table("pos_sessions")
