"""foundation hardening modules business inventory

Revision ID: 8d72a64c9f31
Revises: 3b7c2f4e9a10
Create Date: 2026-06-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "8d72a64c9f31"
down_revision = "3b7c2f4e9a10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "businesses",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=True),
        sa.Column("public_name", sa.String(length=200), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("website_url", sa.String(length=255), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=80), nullable=True),
        sa.Column("postal_code", sa.String(length=40), nullable=True),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_businesses_slug"), "businesses", ["slug"], unique=True)

    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feature_flags_business_id"), "feature_flags", ["business_id"], unique=False)
    op.create_index(op.f("ix_feature_flags_key"), "feature_flags", ["key"], unique=True)

    op.create_table(
        "inventory_movements",
        sa.Column("inventory_record_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("variant_id", sa.Integer(), nullable=True),
        sa.Column("from_location_id", sa.Integer(), nullable=True),
        sa.Column("to_location_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("movement_type", sa.Enum("ADJUSTMENT", "TRANSFER_IN", "TRANSFER_OUT", "RESERVATION", "RELEASE", "DEDUCTION", "RETURN", native_enum=False, length=40), nullable=False),
        sa.Column("reference_type", sa.String(length=80), nullable=True),
        sa.Column("reference_id", sa.String(length=80), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["from_location_id"], ["inventory_locations.id"]),
        sa.ForeignKeyConstraint(["inventory_record_id"], ["inventory_records.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["to_location_id"], ["inventory_locations.id"]),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("actor_id", "from_location_id", "inventory_record_id", "movement_type", "product_id", "reference_id", "reference_type", "to_location_id", "variant_id"):
        op.create_index(op.f(f"ix_inventory_movements_{column}"), "inventory_movements", [column], unique=False)

    op.create_table(
        "prep_task_templates",
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.Enum("INVENTORY", "REPRINT", "SUPPLY", "CASH_BOX", "SIGNAGE", "PAYMENT_DEVICE", "STAFFING", "GENERAL", native_enum=False, length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_due_days_before", sa.Integer(), nullable=False),
        sa.Column("default_enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_prep_task_templates_category"), "prep_task_templates", ["category"], unique=False)

    op.create_table(
        "prep_tasks",
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.Enum("INVENTORY", "REPRINT", "SUPPLY", "CASH_BOX", "SIGNAGE", "PAYMENT_DEVICE", "STAFFING", "GENERAL", native_enum=False, length=40), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "IN_PROGRESS", "COMPLETED", "REOPENED", "CANCELED", native_enum=False, length=40), nullable=False),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["prep_task_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("assigned_user_id", "category", "completed_at", "due_at", "market_id", "status", "template_id"):
        op.create_index(op.f(f"ix_prep_tasks_{column}"), "prep_tasks", [column], unique=False)

    for table in (
        "products",
        "product_variants",
        "filament_spools",
        "inventory_locations",
        "inventory_records",
        "orders",
        "pos_sessions",
        "receipts",
        "expenses",
        "markets",
    ):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("business_id", sa.Integer(), nullable=True))
            batch_op.create_index(op.f(f"ix_{table}_business_id"), ["business_id"], unique=False)
            batch_op.create_foreign_key(
                op.f(f"fk_{table}_business_id_businesses"),
                "businesses",
                ["business_id"],
                ["id"],
            )


def downgrade():
    for table in (
        "markets",
        "expenses",
        "receipts",
        "pos_sessions",
        "orders",
        "inventory_records",
        "inventory_locations",
        "filament_spools",
        "product_variants",
        "products",
    ):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(op.f(f"fk_{table}_business_id_businesses"), type_="foreignkey")
            batch_op.drop_index(op.f(f"ix_{table}_business_id"))
            batch_op.drop_column("business_id")

    op.drop_table("prep_tasks")
    op.drop_table("prep_task_templates")
    op.drop_table("inventory_movements")
    op.drop_table("feature_flags")
    op.drop_index(op.f("ix_businesses_slug"), table_name="businesses")
    op.drop_table("businesses")
