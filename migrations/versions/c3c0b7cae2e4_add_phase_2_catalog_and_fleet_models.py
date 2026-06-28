"""Add phase 2 catalog and fleet models

Revision ID: c3c0b7cae2e4
Revises: 25026b2d9165
Create Date: 2026-06-11 22:45:10.226203

"""

from alembic import op
import sqlalchemy as sa


revision = "c3c0b7cae2e4"
down_revision = "25026b2d9165"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "categories",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("is_pos_visible", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_categories_slug"), ["slug"], unique=True)

    op.create_table(
        "collections",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("collections", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_collections_slug"), ["slug"], unique=True)

    op.create_table(
        "filament_spools",
        sa.Column("brand", sa.String(length=160), nullable=False),
        sa.Column("material_type", sa.String(length=120), nullable=False),
        sa.Column("color_name", sa.String(length=120), nullable=False),
        sa.Column("color_hex", sa.String(length=7), nullable=True),
        sa.Column("spool_weight_grams", sa.Integer(), nullable=False),
        sa.Column("remaining_weight_grams", sa.Integer(), nullable=False),
        sa.Column("cost_per_spool", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("cost_per_gram", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("supplier", sa.String(length=160), nullable=True),
        sa.Column("purchase_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storage_location", sa.String(length=160), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "NEW",
                "ACTIVE",
                "LOW",
                "EMPTY",
                "ARCHIVED",
                name="filamentstatus",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("reorder_threshold_grams", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "inventory_locations",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("type", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("inventory_locations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_inventory_locations_name"), ["name"], unique=True)

    op.create_table(
        "printers",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("serial_number", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "IDLE",
                "PRINTING",
                "MAINTENANCE",
                "BROKEN",
                "RETIRED",
                name="printerstatus",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("location", sa.String(length=160), nullable=True),
        sa.Column("has_ams", sa.Boolean(), nullable=False),
        sa.Column("default_nozzle_size", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("purchase_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("maintenance_notes", sa.Text(), nullable=True),
        sa.Column("total_print_hours", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("serial_number"),
    )
    with op.batch_alter_table("printers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_printers_name"), ["name"], unique=True)
        batch_op.create_index(batch_op.f("ix_printers_status"), ["status"], unique=False)

    op.create_table(
        "ams_units",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "type",
            sa.Enum("AMS_LITE", "STANDARD_AMS", name="amsunittype", native_enum=False, length=40),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "ASSIGNED",
                "MAINTENANCE",
                "BROKEN",
                "RETIRED",
                name="amsunitstatus",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("assigned_printer_id", sa.Integer(), nullable=True),
        sa.Column("slot_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_printer_id"], ["printers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ams_units", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ams_units_assigned_printer_id"), ["assigned_printer_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_ams_units_name"), ["name"], unique=True)

    op.create_table(
        "api_tokens",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_api_tokens_prefix"), ["prefix"], unique=False)
        batch_op.create_index(batch_op.f("ix_api_tokens_token_hash"), ["token_hash"], unique=True)
        batch_op.create_index(batch_op.f("ix_api_tokens_user_id"), ["user_id"], unique=False)

    op.create_table(
        "products",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("sku_base", sa.String(length=80), nullable=True),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=True),
        sa.Column(
            "product_type",
            sa.Enum(
                "FINISHED_GOOD",
                "CUSTOMIZABLE_PRODUCT",
                "MADE_TO_ORDER_PRODUCT",
                "POS_QUICK_ITEM",
                "B2B_PRODUCT",
                "INTERNAL_ONLY",
                name="producttype",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "ACTIVE",
                "HIDDEN",
                "RETIRED",
                "NEEDS_REVIEW",
                name="productstatus",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("is_pos_visible", sa.Boolean(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False),
        sa.Column("base_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("estimated_material_cost", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("estimated_labor_minutes", sa.Integer(), nullable=False),
        sa.Column("estimated_print_minutes", sa.Integer(), nullable=False),
        sa.Column("estimated_profit", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("default_image_path", sa.String(length=255), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("care_instructions", sa.Text(), nullable=True),
        sa.Column("safety_notes", sa.Text(), nullable=True),
        sa.Column(
            "license_status",
            sa.Enum(
                "UNKNOWN",
                "PERSONAL_ONLY",
                "COMMERCIAL_ALLOWED",
                "COMMERCIAL_SUBSCRIPTION",
                "CUSTOMER_OWNED",
                "NEEDS_REVIEW",
                "RESTRICTED",
                "RETIRED",
                name="licensestatus",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("design_source", sa.String(length=255), nullable=True),
        sa.Column("commercial_license_notes", sa.Text(), nullable=True),
        sa.Column(
            "model_source_type",
            sa.Enum(
                "SELF_DESIGNED",
                "PURCHASED_STL",
                "SUBSCRIPTION_LIBRARY",
                "FREE_MODEL",
                "CUSTOMER_PROVIDED",
                "COMMISSIONED_DESIGN",
                "UNKNOWN",
                name="modelsourcetype",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("model_source_url", sa.String(length=500), nullable=True),
        sa.Column("model_designer_name", sa.String(length=160), nullable=True),
        sa.Column("model_license_type", sa.String(length=160), nullable=True),
        sa.Column("model_commercial_use_allowed", sa.Boolean(), nullable=False),
        sa.Column("model_license_expiration", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_proof_of_license_path", sa.String(length=255), nullable=True),
        sa.Column("model_file_path", sa.String(length=500), nullable=True),
        sa.Column("model_notes", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_products_category_id"), ["category_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_products_collection_id"), ["collection_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_products_sku_base"), ["sku_base"], unique=True)
        batch_op.create_index(batch_op.f("ix_products_slug"), ["slug"], unique=True)
        batch_op.create_index(batch_op.f("ix_products_status"), ["status"], unique=False)

    op.create_table(
        "inventory_records",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False),
        sa.Column("quantity_reserved", sa.Integer(), nullable=False),
        sa.Column("reorder_threshold", sa.Integer(), nullable=False),
        sa.Column("reorder_target", sa.Integer(), nullable=False),
        sa.Column("last_counted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["inventory_locations.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "location_id",
            name="uq_inventory_records_product_location",
        ),
    )
    with op.batch_alter_table("inventory_records", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_inventory_records_location_id"), ["location_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_inventory_records_product_id"), ["product_id"], unique=False)


def downgrade():
    with op.batch_alter_table("inventory_records", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_inventory_records_product_id"))
        batch_op.drop_index(batch_op.f("ix_inventory_records_location_id"))

    op.drop_table("inventory_records")
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_products_status"))
        batch_op.drop_index(batch_op.f("ix_products_slug"))
        batch_op.drop_index(batch_op.f("ix_products_sku_base"))
        batch_op.drop_index(batch_op.f("ix_products_collection_id"))
        batch_op.drop_index(batch_op.f("ix_products_category_id"))

    op.drop_table("products")
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_api_tokens_user_id"))
        batch_op.drop_index(batch_op.f("ix_api_tokens_token_hash"))
        batch_op.drop_index(batch_op.f("ix_api_tokens_prefix"))

    op.drop_table("api_tokens")
    with op.batch_alter_table("ams_units", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ams_units_name"))
        batch_op.drop_index(batch_op.f("ix_ams_units_assigned_printer_id"))

    op.drop_table("ams_units")
    with op.batch_alter_table("printers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_printers_status"))
        batch_op.drop_index(batch_op.f("ix_printers_name"))

    op.drop_table("printers")
    with op.batch_alter_table("inventory_locations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_inventory_locations_name"))

    op.drop_table("inventory_locations")
    op.drop_table("filament_spools")
    with op.batch_alter_table("collections", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_collections_slug"))

    op.drop_table("collections")
    with op.batch_alter_table("categories", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_categories_slug"))

    op.drop_table("categories")
