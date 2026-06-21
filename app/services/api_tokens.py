from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from sqlalchemy import select

from app.extensions import db
from app.models import ApiToken, User
from app.models.base import utc_now
from app.services.audit import record_audit_event

AVAILABLE_API_TOKEN_SCOPES: tuple[tuple[str, str], ...] = (
    ("catalog", "Catalog: products, categories, collections, variants, model assets"),
    ("inventory", "Inventory: finished goods, filament, and locations"),
    ("orders", "Orders: orders, items, payments, and customers"),
    ("pos", "POS: sessions and sales"),
    ("markets", "Markets: events, packing lists, and market operations"),
    ("receipts", "Receipts & Expenses: receipts and expense ledger"),
    ("analytics", "Analytics: summaries, charts, and insights"),
    ("settings", "Settings: settings, feature flags, modules, and API tokens"),
)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_api_token(
    user: User,
    name: str,
    scopes: list[str] | None = None,
    expires_at: datetime | None = None,
) -> tuple[ApiToken, str]:
    raw_token = secrets.token_urlsafe(32)
    prefix = raw_token[:8]
    token = ApiToken(
        user=user,
        name=name,
        token_hash=_hash_token(raw_token),
        prefix=prefix,
        scopes=",".join(scopes or []),
        expires_at=expires_at,
    )
    db.session.add(token)
    db.session.commit()
    record_audit_event(
        action="api_token.created",
        entity_type="api_token",
        entity_id=token.id,
        after_state={"name": token.name, "prefix": token.prefix, "scopes": token.scopes},
        source_module=__name__,
        actor_id=user.id,
    )
    return token, raw_token


def authenticate_api_token(raw_token: str) -> ApiToken | None:
    statement = select(ApiToken).where(ApiToken.token_hash == _hash_token(raw_token))
    token = db.session.scalar(statement)
    if token is None or not token.is_active:
        return None

    token.last_used_at = utc_now()
    db.session.commit()
    return token
