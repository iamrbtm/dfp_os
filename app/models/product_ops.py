from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class ProductLaunchChecklistKey(StrEnum):
    LICENSE_VERIFIED = "license_verified"
    MODEL_ANALYZED = "model_analyzed"
    COST_SNAPSHOT = "cost_snapshot"
    PRODUCT_PHOTOS = "product_photos"
    POS_TILE = "pos_tile"
    PUBLIC_DESCRIPTION = "public_description"
    INVENTORY_TARGET = "inventory_target"
    MARKET_TEST_PLAN = "market_test_plan"
    SAFETY_CARE_NOTES = "safety_care_notes"


class ProductPhotoShotType(StrEnum):
    HERO = "hero"
    SCALE_IN_HAND = "scale_in_hand"
    COLOR_VARIANTS = "color_variants"
    CLOSE_UP = "close_up"
    PACKAGING = "packaging"
    BOOTH_DISPLAY = "booth_display"
    POS_TILE = "pos_tile"


class DeadStockRecommendationStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    ACTIONED = "actioned"


class ProductLaunchChecklistItem(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "product_launch_checklist_items"
    __table_args__ = (
        UniqueConstraint("product_id", "key", name="uq_product_launch_checklist_product_key"),
    )

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    key: Mapped[ProductLaunchChecklistKey] = mapped_column(
        Enum(ProductLaunchChecklistKey, values_callable=lambda e: [m.value for m in e], length=60),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product = relationship("Product", back_populates="launch_checklist_items")


class ProductPhotoShot(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "product_photo_shots"
    __table_args__ = (
        UniqueConstraint("product_id", "shot_type", name="uq_product_photo_shots_product_type"),
    )

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    shot_type: Mapped[ProductPhotoShotType] = mapped_column(
        Enum(ProductPhotoShotType, values_callable=lambda e: [m.value for m in e], length=60),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    image_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product = relationship("Product", back_populates="photo_shots")


class DeadStockRecommendation(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "dead_stock_recommendations"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    suggested_action: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DeadStockRecommendationStatus] = mapped_column(
        Enum(DeadStockRecommendationStatus, values_callable=lambda e: [m.value for m in e], length=40),
        default=DeadStockRecommendationStatus.OPEN,
        nullable=False,
        index=True,
    )
    action_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    product = relationship("Product", back_populates="dead_stock_recommendations")
