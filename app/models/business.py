from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class Business(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    public_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default="America/Chicago", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    customers = relationship("Customer", back_populates="business")
    print_jobs = relationship("PrintJob", back_populates="business")
    filament_spools = relationship("FilamentSpool", back_populates="business")
    inventory_locations = relationship("InventoryLocation", back_populates="business")
    inventory_records = relationship("InventoryRecord", back_populates="business")
    prep_task_templates = relationship("PrepTaskTemplate", back_populates="business")
    prep_tasks = relationship("PrepTask", back_populates="business")
    custom_requests = relationship("CustomRequest", back_populates="business")
    notifications = relationship("Notification", back_populates="business")


class FeatureFlag(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_id: Mapped[int | None] = mapped_column(db.ForeignKey("businesses.id"), nullable=True, index=True)
    business = relationship("Business")
