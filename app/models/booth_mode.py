from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class BoothHintStatus(StrEnum):
    OPEN = "open"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"
    ACCEPTED = "accepted"


class BoothModeHint(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "booth_mode_hints"

    market_id: Mapped[int | None] = mapped_column(ForeignKey("markets.id"), nullable=True, index=True)
    pos_session_id: Mapped[int | None] = mapped_column(ForeignKey("pos_sessions.id"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    status: Mapped[BoothHintStatus] = mapped_column(
        Enum(BoothHintStatus, native_enum=False, length=40),
        default=BoothHintStatus.OPEN,
        nullable=False,
        index=True,
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    market = relationship("Market")
    pos_session = relationship("PosSession")
