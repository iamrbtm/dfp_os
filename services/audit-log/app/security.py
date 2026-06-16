from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings


async def verify_internal_token(authorization: str | None = Header(None)) -> None:
    """Dependency that verifies the internal bearer token on protected endpoints."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "missing_auth_header", "message": "Authorization header must use Bearer scheme."},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "missing_auth_header", "message": "Authorization header must use Bearer scheme."},
        )
    if token != settings.internal_api_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "invalid_token", "message": "The provided internal token is invalid."},
        )
