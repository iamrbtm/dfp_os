from __future__ import annotations

import hmac
from typing import Iterable

from fastapi import Header, HTTPException, Query, status

from app.config import settings

SCOPE_READ = "trend_scout:read"
SCOPE_WRITE = "trend_scout:write"
SCOPE_ADMIN = "trend_scout:admin"

ALL_SCOPES: tuple[str, ...] = (SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN)


def _extract_bearer(
    authorization: str | None,
    token: str | None,
) -> str | None:
    raw = authorization
    if raw is None or not raw.startswith("Bearer "):
        if token:
            raw = f"Bearer {token}"
    if raw is None or not raw.startswith("Bearer "):
        return None
    parsed = raw.removeprefix("Bearer ").strip()
    return parsed or None


async def verify_internal_token(
    authorization: str | None = Header(None),
    token: str | None = Query(
        None,
        description="Bearer token as query param (alternative to Authorization header)",
    ),
) -> None:
    parsed = _extract_bearer(authorization, token)
    if parsed is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "missing_auth_header",
                "message": "Authorization header or ?token= query param required.",
            },
        )
    if not hmac.compare_digest(parsed, settings.internal_api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_token",
                "message": "The provided internal token is invalid.",
            },
        )


def require_scopes(*required: str):
    """Dependency factory that asserts the caller has all required scopes.

    The current single-token model has all scopes for the internal API token.
    Per-token scope grants are not yet wired (Phase 5 may add this)."""

    async def _checker(
        authorization: str | None = Header(None),
        token: str | None = Query(None),
    ) -> None:
        parsed = _extract_bearer(authorization, token)
        if parsed is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "missing_auth_header",
                    "message": "Authorization header or ?token= query param required.",
                },
            )
        if not hmac.compare_digest(parsed, settings.internal_api_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_token", "message": "Invalid token."},
            )

    return _checker


def has_scopes(token_scopes: Iterable[str], required: Iterable[str]) -> bool:
    return all(s in token_scopes for s in required)
