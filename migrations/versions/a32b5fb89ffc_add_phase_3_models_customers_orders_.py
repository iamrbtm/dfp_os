"""Add Phase 3 models: customers, orders, payments, print jobs

Revision ID: a32b5fb89ffc
Revises: c3c0b7cae2e4
Create Date: 2026-06-13 22:24:44.953899

"""

from alembic import op
import sqlalchemy as sa


revision = "a32b5fb89ffc"
down_revision = "c3c0b7cae2e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customers",
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("address_line_1", sa.String(length=255), nullable=True),
        sa.Column("address_line_2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("zip_code", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_customers_email"), "customers", ["email"], unique=False)

    op.create_table(
        "orders",
        sa.Column("order_number", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "CONFIRMED",
                "PRINTING",
                "COMPLETED",
                "CANCELLED",
                "REFUNDED",
                name="orderstatus",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum("POS", "ONLINE", "CUSTOM", "MANUAL", "MARKET", name="ordersource", native_enum=False, length=40),
            nullable=False,
        ),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("pos_session_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("tax_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("discount_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("paid_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_customer_id"), "orders", ["customer_id"], unique=False)
    op.create_index(op.f("ix_orders_market_id"), "orders", ["market_id"], unique=False)
    op.create_index(op.f("ix_orders_order_number"), "orders", ["order_number"], unique=True)
    op.create_index(op.f("ix_orders_pos_session_id"), "orders", ["pos_session_id"], unique=False)
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)

    op.create_table(
        "custom_requests",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reference_image_paths", sa.Text(), nullable=True),
        sa.Column("estimated_budget", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "NEW",
                "QUOTED",
                "APPROVED",
                "DEPOSIT_COLLECTED",
                "IN_PROGRESS",
                "COMPLETED",
                "CANCELLED",
                "ARCHIVED",
                name="customrequeststatus",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("converted_to_order_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["converted_to_order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_custom_requests_converted_to_order_id"), "custom_requests", ["converted_to_order_id"], unique=False)
    op.create_index(op.f("ix_custom_requests_customer_id"), "custom_requests", ["customer_id"], unique=False)
    op.create_index(op.f("ix_custom_requests_status"), "custom_requests", ["status"], unique=False)

    op.create_table(
        "payments",
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "method",
            sa.Enum("CASH", "CARD_EXTERNAL", "VENMO", "CASH_APP", "APPLE_PAY", "OTHER", name="paymentmethod", native_enum=False, length=40),
            nullable=False,
        ),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("payment_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payments_order_id"), "payments", ["order_id"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("is_custom_item", sa.Boolean(), nullable=False),
        sa.Column("custom_description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)
    op.create_index(op.f("ix_order_items_product_id"), "order_items", ["product_id"], unique=False)

    op.create_table(
        "print_jobs",
        sa.Column("order_item_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("printer_id", sa.Integer(), nullable=True),
        sa.Column("assigned_to_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("QUEUED", "PRINTING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED", name="printjobstatus", native_enum=False, length=40),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("actual_minutes", sa.Integer(), nullable=True),
        sa.Column("filament_used_grams", sa.Integer(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"]),
        sa.ForeignKeyConstraint(["printer_id"], ["printers.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_print_jobs_assigned_to_id"), "print_jobs", ["assigned_to_id"], unique=False)
    op.create_index(op.f("ix_print_jobs_order_item_id"), "print_jobs", ["order_item_id"], unique=False)
    op.create_index(op.f("ix_print_jobs_printer_id"), "print_jobs", ["printer_id"], unique=False)
    op.create_index(op.f("ix_print_jobs_product_id"), "print_jobs", ["product_id"], unique=False)
    op.create_index(op.f("ix_print_jobs_status"), "print_jobs", ["status"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_print_jobs_status"), table_name="print_jobs")
    op.drop_index(op.f("ix_print_jobs_product_id"), table_name="print_jobs")
    op.drop_index(op.f("ix_print_jobs_printer_id"), table_name="print_jobs")
    op.drop_index(op.f("ix_print_jobs_order_item_id"), table_name="print_jobs")
    op.drop_index(op.f("ix_print_jobs_assigned_to_id"), table_name="print_jobs")
    op.drop_table("print_jobs")
    op.drop_index(op.f("ix_order_items_product_id"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items")
    op.drop_table("order_items")
    op.drop_index(op.f("ix_payments_order_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_custom_requests_status"), table_name="custom_requests")
    op.drop_index(op.f("ix_custom_requests_customer_id"), table_name="custom_requests")
    op.drop_index(op.f("ix_custom_requests_converted_to_order_id"), table_name="custom_requests")
    op.drop_table("custom_requests")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_pos_session_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_order_number"), table_name="orders")
    op.drop_index(op.f("ix_orders_market_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_customer_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_index(op.f("ix_customers_email"), table_name="customers")
    op.drop_table("customers")
