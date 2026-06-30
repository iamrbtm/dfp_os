from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class InternalDemandEventType(StrEnum):
    STOREFRONT_SEARCH = "storefront_search_performed"
    PRODUCT_VIEWED = "product_viewed"
    PRODUCT_ADDED_TO_CART = "product_added_to_cart"
    CART_UPDATED = "cart_updated"
    CART_REMOVED = "cart_removed"
    CHECKOUT_STARTED = "checkout_started"
    ONLINE_ORDER_CREATED = "online_order_created"
    CUSTOM_REQUEST_SUBMITTED = "custom_request_submitted"
    POS_SALE_COMPLETED = "pos_sale_completed"
    MANUAL_CUSTOMER_REQUEST_LOGGED = "manual_customer_request_logged"


class InternalDemandEvent(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "internal_demand_events"

    event_type: Mapped[InternalDemandEventType] = mapped_column(
        Enum(InternalDemandEventType, native_enum=False, length=80),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc), nullable=False, index=True
    )
    keyword: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id"), nullable=True, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id"), nullable=True, index=True
    )
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    custom_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_requests.id"), nullable=True, index=True
    )
    quantity: Mapped[int | None] = mapped_column(nullable=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    session_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    text_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    extracted_terms: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product = relationship("Product")
    category = relationship("Category")
    collection = relationship("Collection")
    order = relationship("Order")
    custom_request = relationship("CustomRequest")
