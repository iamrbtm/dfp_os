from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin


class Setting(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    setting_type: Mapped[str] = mapped_column("type", String(20), nullable=False, default="string")

    def __repr__(self) -> str:
        return f"<Setting {self.key}={self.value}>"
