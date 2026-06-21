"""Add market command center tables

Revision ID: 2f9a1b7c4d8e
Revises: 0e8b440db6b9
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "2f9a1b7c4d8e"
down_revision = "0e8b440db6b9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("markets") as batch_op:
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("application_submitted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("application_approved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("fee_paid_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("booth_location", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("booth_size", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("power_available", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("wifi_available", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("food_available", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("load_in_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("load_out_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("load_in_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("load_out_notes", sa.Text(), nullable=True))

    op.create_table(
        "market_timeline_events",
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("event_type", sa.Enum("SETUP", "MARKET_HOURS", "LOAD_IN", "LOAD_OUT", "DEADLINE", "REMINDER", "OTHER", name="markettimelineeventtype", native_enum=False, length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_market_timeline_events_market_id"), "market_timeline_events", ["market_id"], unique=False)
    op.create_index(op.f("ix_market_timeline_events_starts_at"), "market_timeline_events", ["starts_at"], unique=False)
    op.create_index(op.f("ix_market_timeline_events_event_type"), "market_timeline_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_market_timeline_events_completed_at"), "market_timeline_events", ["completed_at"], unique=False)

    op.create_table(
        "market_tasks",
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("task_type", sa.Enum("TODO", "MARKETING", "APPLICATION", "PAYMENT", "PACKING", "FOLLOW_UP", name="markettasktype", native_enum=False, length=40), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "IN_PROGRESS", "COMPLETED", "CANCELED", name="markettaskstatus", native_enum=False, length=40), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_market_tasks_market_id"), "market_tasks", ["market_id"], unique=False)
    op.create_index(op.f("ix_market_tasks_task_type"), "market_tasks", ["task_type"], unique=False)
    op.create_index(op.f("ix_market_tasks_status"), "market_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_market_tasks_due_at"), "market_tasks", ["due_at"], unique=False)
    op.create_index(op.f("ix_market_tasks_completed_at"), "market_tasks", ["completed_at"], unique=False)

    op.create_table(
        "market_weather_snapshots",
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("temperature", sa.Integer(), nullable=True),
        sa.Column("short_forecast", sa.String(length=255), nullable=True),
        sa.Column("detailed_forecast", sa.Text(), nullable=True),
        sa.Column("precipitation_probability", sa.Integer(), nullable=True),
        sa.Column("wind_speed", sa.String(length=80), nullable=True),
        sa.Column("wind_direction", sa.String(length=30), nullable=True),
        sa.Column("alert_summary", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_market_weather_snapshots_market_id"), "market_weather_snapshots", ["market_id"], unique=False)
    op.create_index(op.f("ix_market_weather_snapshots_forecast_for"), "market_weather_snapshots", ["forecast_for"], unique=False)

    op.create_table(
        "market_hotel_bookings",
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("hotel_name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("check_in_date", sa.Date(), nullable=True),
        sa.Column("check_out_date", sa.Date(), nullable=True),
        sa.Column("confirmation_number", sa.String(length=120), nullable=True),
        sa.Column("cost", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("status", sa.Enum("PLANNED", "BOOKED", "CANCELED", "COMPLETED", name="markethotelbookingstatus", native_enum=False, length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_market_hotel_bookings_market_id"), "market_hotel_bookings", ["market_id"], unique=False)
    op.create_index(op.f("ix_market_hotel_bookings_status"), "market_hotel_bookings", ["status"], unique=False)

    op.create_table(
        "market_documents",
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("document_type", sa.Enum("APPLICATION", "PERMIT", "RECEIPT", "MAP", "CONTRACT", "MARKETING", "OTHER", name="marketdocumenttype", native_enum=False, length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_market_documents_market_id"), "market_documents", ["market_id"], unique=False)
    op.create_index(op.f("ix_market_documents_document_type"), "market_documents", ["document_type"], unique=False)
    op.create_index(op.f("ix_market_documents_uploaded_by_user_id"), "market_documents", ["uploaded_by_user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_market_documents_uploaded_by_user_id"), table_name="market_documents")
    op.drop_index(op.f("ix_market_documents_document_type"), table_name="market_documents")
    op.drop_index(op.f("ix_market_documents_market_id"), table_name="market_documents")
    op.drop_table("market_documents")
    op.drop_index(op.f("ix_market_hotel_bookings_status"), table_name="market_hotel_bookings")
    op.drop_index(op.f("ix_market_hotel_bookings_market_id"), table_name="market_hotel_bookings")
    op.drop_table("market_hotel_bookings")
    op.drop_index(op.f("ix_market_weather_snapshots_forecast_for"), table_name="market_weather_snapshots")
    op.drop_index(op.f("ix_market_weather_snapshots_market_id"), table_name="market_weather_snapshots")
    op.drop_table("market_weather_snapshots")
    op.drop_index(op.f("ix_market_tasks_completed_at"), table_name="market_tasks")
    op.drop_index(op.f("ix_market_tasks_due_at"), table_name="market_tasks")
    op.drop_index(op.f("ix_market_tasks_status"), table_name="market_tasks")
    op.drop_index(op.f("ix_market_tasks_task_type"), table_name="market_tasks")
    op.drop_index(op.f("ix_market_tasks_market_id"), table_name="market_tasks")
    op.drop_table("market_tasks")
    op.drop_index(op.f("ix_market_timeline_events_completed_at"), table_name="market_timeline_events")
    op.drop_index(op.f("ix_market_timeline_events_event_type"), table_name="market_timeline_events")
    op.drop_index(op.f("ix_market_timeline_events_starts_at"), table_name="market_timeline_events")
    op.drop_index(op.f("ix_market_timeline_events_market_id"), table_name="market_timeline_events")
    op.drop_table("market_timeline_events")
    with op.batch_alter_table("markets") as batch_op:
        batch_op.drop_column("load_out_notes")
        batch_op.drop_column("load_in_notes")
        batch_op.drop_column("load_out_at")
        batch_op.drop_column("load_in_at")
        batch_op.drop_column("food_available")
        batch_op.drop_column("wifi_available")
        batch_op.drop_column("power_available")
        batch_op.drop_column("booth_size")
        batch_op.drop_column("booth_location")
        batch_op.drop_column("fee_paid_at")
        batch_op.drop_column("application_approved_at")
        batch_op.drop_column("application_submitted_at")
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
