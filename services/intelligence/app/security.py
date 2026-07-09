from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.config import settings


async def verify_internal_token(
    authorization: str | None = Header(None),
) -> None:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_auth_header", "message": "Authorization bearer token is required."},
        )
    parsed = authorization.removeprefix("Bearer ").strip()
    expected = settings.internal_api_token or ""
    if not parsed or not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_auth_header", "message": "Authorization bearer token is required."},
        )
    if not hmac.compare_digest(parsed, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "The provided internal token is invalid."},
        )
