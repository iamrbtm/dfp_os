"""add pickup scheduler

Revision ID: 0f1e2d3c4b5a
Revises: f4a5b6c7d8e9
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0f1e2d3c4b5a"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pickup_locations",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("location_type", sa.String(length=40), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pickup_locations_active", "pickup_locations", ["active"])
    op.create_index("ix_pickup_locations_location_type", "pickup_locations", ["location_type"])
    op.create_index("ix_pickup_locations_name", "pickup_locations", ["name"])

    op.create_table(
        "pickup_slots",
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default=sa.text("6")),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("public_label", sa.String(length=200), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["pickup_locations.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pickup_slots_ends_at", "pickup_slots", ["ends_at"])
    op.create_index("ix_pickup_slots_location_id", "pickup_slots", ["location_id"])
    op.create_index("ix_pickup_slots_market_id", "pickup_slots", ["market_id"])
    op.create_index("ix_pickup_slots_starts_at", "pickup_slots", ["starts_at"])
    op.create_index("ix_pickup_slots_status", "pickup_slots", ["status"])

    for table_name in ("orders", "custom_requests"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("pickup_slot_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("pickup_status", sa.String(length=40), nullable=True))
            batch_op.add_column(sa.Column("pickup_ready_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("pickup_no_show_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("pickup_notes", sa.Text(), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table_name}_pickup_slot_id_pickup_slots",
                "pickup_slots",
                ["pickup_slot_id"],
                ["id"],
            )
            batch_op.create_index(f"ix_{table_name}_pickup_slot_id", ["pickup_slot_id"])
            batch_op.create_index(f"ix_{table_name}_pickup_status", ["pickup_status"])


def downgrade():
    for table_name in ("custom_requests", "orders"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_pickup_status")
            batch_op.drop_index(f"ix_{table_name}_pickup_slot_id")
            batch_op.drop_constraint(f"fk_{table_name}_pickup_slot_id_pickup_slots", type_="foreignkey")
            batch_op.drop_column("pickup_notes")
            batch_op.drop_column("pickup_no_show_at")
            batch_op.drop_column("picked_up_at")
            batch_op.drop_column("pickup_ready_at")
            batch_op.drop_column("pickup_status")
            batch_op.drop_column("pickup_slot_id")

    op.drop_index("ix_pickup_slots_status", table_name="pickup_slots")
    op.drop_index("ix_pickup_slots_starts_at", table_name="pickup_slots")
    op.drop_index("ix_pickup_slots_market_id", table_name="pickup_slots")
    op.drop_index("ix_pickup_slots_location_id", table_name="pickup_slots")
    op.drop_index("ix_pickup_slots_ends_at", table_name="pickup_slots")
    op.drop_table("pickup_slots")

    op.drop_index("ix_pickup_locations_name", table_name="pickup_locations")
    op.drop_index("ix_pickup_locations_location_type", table_name="pickup_locations")
    op.drop_index("ix_pickup_locations_active", table_name="pickup_locations")
    op.drop_table("pickup_locations")
