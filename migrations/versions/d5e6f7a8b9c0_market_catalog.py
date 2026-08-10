"""market catalog

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-10 00:00:00.000000

Adds the Market Catalog discovery pool: market_categories, market_catalog_listings,
market_catalog_booth_tiers, and a nullable FK from markets to market_catalog_listings.
Seeds default market categories.
"""

from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


DEFAULT_CATEGORIES = [
    ("Holiday", "holiday", 1),
    ("Flea", "flea", 2),
    ("Craft", "craft", 3),
    ("Farmers", "farmers", 4),
    ("Art", "art", 5),
    ("Antique/Vintage", "antique-vintage", 6),
    ("Festival", "festival", 7),
    ("Trade Show", "trade-show", 8),
    ("Pop-up", "pop-up", 9),
    ("Night Market", "night-market", 10),
    ("Other", "other", 99),
]


def upgrade():
    op.create_table(
        "market_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_market_categories_name"),
        sa.UniqueConstraint("slug", name="uq_market_categories_slug"),
    )
    op.create_index("ix_market_categories_name", "market_categories", ["name"])
    op.create_index("ix_market_categories_slug", "market_categories", ["slug"])

    op.create_table(
        "market_catalog_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(220), nullable=False),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("market_categories.id"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("location_name", sa.String(200), nullable=True),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(50), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("default_start_time", sa.Time(), nullable=True),
        sa.Column("default_end_time", sa.Time(), nullable=True),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="America/Chicago"),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("rrule", sa.Text(), nullable=True),
        sa.Column("recurrence_description", sa.String(255), nullable=True),
        sa.Column("next_occurrence_date", sa.Date(), nullable=True),
        sa.Column("last_occurrence_date", sa.Date(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_vendor_count", sa.Integer(), nullable=True),
        sa.Column("estimated_attendee_count", sa.Integer(), nullable=True),
        sa.Column("power_available", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("wifi_available", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("food_available", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("restrooms_available", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("indoor", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("covered_outdoor", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("outdoor", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("parking_notes", sa.Text(), nullable=True),
        sa.Column("organizer_name", sa.String(200), nullable=True),
        sa.Column("organizer_email", sa.String(200), nullable=True),
        sa.Column("organizer_phone", sa.String(60), nullable=True),
        sa.Column("application_url", sa.String(500), nullable=True),
        sa.Column("application_contact", sa.String(200), nullable=True),
        sa.Column("application_deadline_description", sa.String(255), nullable=True),
        sa.Column("booth_rules", sa.Text(), nullable=True),
        sa.Column("required_documents", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("interest_level", sa.String(40), nullable=False, server_default="watching"),
        sa.Column(
            "business_id",
            sa.Integer(),
            sa.ForeignKey("businesses.id"),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_market_catalog_listings_slug"),
    )
    op.create_index("ix_market_catalog_listings_name", "market_catalog_listings", ["name"])
    op.create_index("ix_market_catalog_listings_slug", "market_catalog_listings", ["slug"])
    op.create_index(
        "ix_market_catalog_listings_category_id",
        "market_catalog_listings",
        ["category_id"],
    )
    op.create_index(
        "ix_market_catalog_listings_next_occurrence_date",
        "market_catalog_listings",
        ["next_occurrence_date"],
    )
    op.create_index(
        "ix_market_catalog_listings_interest_level",
        "market_catalog_listings",
        ["interest_level"],
    )
    op.create_index(
        "ix_market_catalog_listings_business_id",
        "market_catalog_listings",
        ["business_id"],
    )

    op.create_table(
        "market_catalog_booth_tiers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "listing_id",
            sa.Integer(),
            sa.ForeignKey("market_catalog_listings.id"),
            nullable=False,
        ),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("dimensions", sa.String(80), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("corner_premium", sa.Numeric(10, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_market_catalog_booth_tiers_listing_id",
        "market_catalog_booth_tiers",
        ["listing_id"],
    )

    op.add_column(
        "markets",
        sa.Column(
            "market_catalog_listing_id",
            sa.Integer(),
            sa.ForeignKey("market_catalog_listings.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_markets_market_catalog_listing_id",
        "markets",
        ["market_catalog_listing_id"],
    )

    # Seed default categories
    op.execute(
        "INSERT INTO market_categories (name, slug, description, sort_order, is_active, "
        "created_at, updated_at) VALUES "
        + ", ".join(
            f"('{name}', '{slug}', NULL, {order}, 1, now(), now())"
            for name, slug, order in DEFAULT_CATEGORIES
        )
    )


def downgrade():
    op.drop_index("ix_markets_market_catalog_listing_id", table_name="markets")
    op.drop_column("markets", "market_catalog_listing_id")
    op.drop_index(
        "ix_market_catalog_booth_tiers_listing_id", table_name="market_catalog_booth_tiers"
    )
    op.drop_table("market_catalog_booth_tiers")
    op.drop_index(
        "ix_market_catalog_listings_business_id", table_name="market_catalog_listings"
    )
    op.drop_index(
        "ix_market_catalog_listings_interest_level", table_name="market_catalog_listings"
    )
    op.drop_index(
        "ix_market_catalog_listings_next_occurrence_date", table_name="market_catalog_listings"
    )
    op.drop_index(
        "ix_market_catalog_listings_category_id", table_name="market_catalog_listings"
    )
    op.drop_index("ix_market_catalog_listings_slug", table_name="market_catalog_listings")
    op.drop_index("ix_market_catalog_listings_name", table_name="market_catalog_listings")
    op.drop_table("market_catalog_listings")
    op.drop_index("ix_market_categories_slug", table_name="market_categories")
    op.drop_index("ix_market_categories_name", table_name="market_categories")
    op.drop_table("market_categories")