from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import PrimaryKeyMixin, TimestampMixin, utc_now


class ApiToken(PrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "api_tokens"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    prefix: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    scopes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_tokens")

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None:
            now = utc_now()
            expires = self.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if expires <= now:
                return False
        return True

    @property
    def scope_set(self) -> set[str]:
        return {scope.strip() for scope in (self.scopes or "").split(",") if scope.strip()}

    def has_scope(self, *required_scopes: str) -> bool:
        token_scopes = self.scope_set
        if not token_scopes:
            return False
        if token_scopes.intersection({"admin", "all"}):
            return True
        return any(scope in token_scopes for scope in required_scopes)
