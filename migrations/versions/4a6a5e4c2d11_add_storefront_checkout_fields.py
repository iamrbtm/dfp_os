"""Add storefront checkout fields to orders

Revision ID: 4a6a5e4c2d11
Revises: 8d72a64c9f31
Create Date: 2026-06-20 10:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4a6a5e4c2d11"
down_revision = "8d72a64c9f31"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column(
            "payment_status",
            sa.Enum(
                "UNPAID",
                "PENDING",
                "PAID",
                "FAILED",
                "REFUNDED",
                name="orderpaymentstatus",
                native_enum=False,
                length=40,
            ),
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "fulfillment_method",
            sa.Enum(
                "PICKUP",
                "SHIPPING",
                name="orderfulfillmentmethod",
                native_enum=False,
                length=40,
            ),
            nullable=False,
            server_default="PICKUP",
        ),
    )
    op.add_column("orders", sa.Column("customer_name", sa.String(length=255), nullable=True))
    op.add_column("orders", sa.Column("customer_email", sa.String(length=255), nullable=True))
    op.add_column("orders", sa.Column("customer_phone", sa.String(length=50), nullable=True))
    op.add_column("orders", sa.Column("shipping_name", sa.String(length=255), nullable=True))
    op.add_column("orders", sa.Column("shipping_address_line_1", sa.String(length=255), nullable=True))
    op.add_column("orders", sa.Column("shipping_address_line_2", sa.String(length=255), nullable=True))
    op.add_column("orders", sa.Column("shipping_city", sa.String(length=120), nullable=True))
    op.add_column("orders", sa.Column("shipping_state", sa.String(length=120), nullable=True))
    op.add_column("orders", sa.Column("shipping_postal_code", sa.String(length=20), nullable=True))
    op.add_column(
        "orders",
        sa.Column("shipping_total", sa.Numeric(precision=10, scale=2), nullable=False, server_default="0.00"),
    )
    op.add_column("orders", sa.Column("payment_provider", sa.String(length=40), nullable=True))
    op.add_column("orders", sa.Column("external_checkout_id", sa.String(length=120), nullable=True))
    op.add_column("orders", sa.Column("external_checkout_url", sa.String(length=500), nullable=True))
    op.add_column("orders", sa.Column("external_payment_reference", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_orders_payment_status"), "orders", ["payment_status"], unique=False)
    op.create_index(op.f("ix_orders_customer_email"), "orders", ["customer_email"], unique=False)
    op.create_index(op.f("ix_orders_external_checkout_id"), "orders", ["external_checkout_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_orders_external_checkout_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_customer_email"), table_name="orders")
    op.drop_index(op.f("ix_orders_payment_status"), table_name="orders")
    op.drop_column("orders", "external_payment_reference")
    op.drop_column("orders", "external_checkout_url")
    op.drop_column("orders", "external_checkout_id")
    op.drop_column("orders", "payment_provider")
    op.drop_column("orders", "shipping_total")
    op.drop_column("orders", "shipping_postal_code")
    op.drop_column("orders", "shipping_state")
    op.drop_column("orders", "shipping_city")
    op.drop_column("orders", "shipping_address_line_2")
    op.drop_column("orders", "shipping_address_line_1")
    op.drop_column("orders", "shipping_name")
    op.drop_column("orders", "customer_phone")
    op.drop_column("orders", "customer_email")
    op.drop_column("orders", "customer_name")
    op.drop_column("orders", "fulfillment_method")
    op.drop_column("orders", "payment_status")
