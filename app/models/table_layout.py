from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class TableSectionType(StrEnum):
    FRONT_LEFT = "front_left"
    FRONT_CENTER = "front_center"
    FRONT_RIGHT = "front_right"
    BACK_LEFT = "back_left"
    BACK_CENTER = "back_center"
    BACK_RIGHT = "back_right"
    CENTER = "center"
    LEFT_EDGE = "left_edge"
    RIGHT_EDGE = "right_edge"
    DISPLAY_RAISED = "display_raised"
    IMPULSE_TRAY = "impulse_tray"
    CUSTOM = "custom"


class MarketTableLayout(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_table_layouts"

    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    copied_from_layout_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_table_layouts.id"), nullable=True, index=True
    )

    market = relationship("Market", foreign_keys=[market_id])
    copied_from = relationship("MarketTableLayout", remote_side="MarketTableLayout.id", foreign_keys=[copied_from_layout_id])
    sections = relationship(
        "MarketTableSection",
        back_populates="layout",
        order_by="MarketTableSection.sort_order",
        cascade="all, delete-orphan",
    )


class MarketTableSection(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_table_sections"

    layout_id: Mapped[int] = mapped_column(
        ForeignKey("market_table_layouts.id"), nullable=False, index=True
    )
    section_type: Mapped[TableSectionType] = mapped_column(
        Enum(TableSectionType, native_enum=False, length=40),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    layout = relationship("MarketTableLayout", back_populates="sections")
    placements = relationship(
        "MarketTablePlacement",
        back_populates="section",
        cascade="all, delete-orphan",
    )


class MarketTablePlacement(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "market_table_placements"

    section_id: Mapped[int] = mapped_column(
        ForeignKey("market_table_sections.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    section = relationship("MarketTableSection", back_populates="placements")
    product = relationship("Product")
