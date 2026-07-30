from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class ContentStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SignStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    USED = "used"
    ARCHIVED = "archived"


class ContentChannel(StrEnum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    ETSY = "etsy"
    WEBSITE = "website"
    OTHER = "other"


class ContentDraft(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "content_drafts"

    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(60), default="social_post", nullable=False)
    channel: Mapped[ContentChannel] = mapped_column(
        Enum(ContentChannel, native_enum=False, length=40),
        default=ContentChannel.OTHER,
        nullable=False,
        index=True,
    )
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    custom_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_requests.id"), nullable=True, index=True
    )
    planned_publish_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, native_enum=False, length=40),
        default=ContentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product = relationship("Product")
    market = relationship("Market")
    custom_request = relationship("CustomRequest")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])


class SignAsset(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "sign_assets"

    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    subtitle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    price_display: Mapped[str | None] = mapped_column(String(60), nullable=True)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    care_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    qr_target_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    collection_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id"), nullable=True, index=True
    )
    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    layout: Mapped[str] = mapped_column(String(20), default="text", nullable=False)
    ai_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[SignStatus] = mapped_column(
        Enum(SignStatus, native_enum=False, length=40),
        default=SignStatus.DRAFT,
        nullable=False,
        index=True,
    )

    product = relationship("Product")
    collection = relationship("Collection")
    market = relationship("Market")
