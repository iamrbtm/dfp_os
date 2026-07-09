from __future__ import annotations

from fastapi import Header, HTTPException, Query, status

from app.config import settings


async def verify_internal_token(
    authorization: str | None = Header(None),
    token: str | None = Query(None, description="Bearer token as query param (alternative to Authorization header)"),
) -> None:
    raw = authorization
    if raw is None or not raw.startswith("Bearer "):
        if token:
            raw = f"Bearer {token}"
    if raw is None or not raw.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "missing_auth_header", "message": "Authorization header or ?token= query param required."},
        )
    parsed = raw.removeprefix("Bearer ").strip()
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "missing_auth_header", "message": "Authorization header or ?token= query param required."},
        )
    if parsed != settings.internal_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "The provided internal token is invalid."},
        )
