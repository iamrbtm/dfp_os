from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status
from fastapi.routing import APIRoute
from starlette.responses import Response

from app.config import settings


def _authorize_request(request: Request) -> None:
    scheme, separator, provided_token = request.headers.get("Authorization", "").partition(" ")
    valid_scheme = bool(separator) and scheme.lower() == "bearer"
    valid_token = secrets.compare_digest(provided_token, settings.internal_api_token)
    if not (valid_scheme and valid_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "A valid bearer token is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_bearer_token(request: Request) -> None:
    """Validate the internal token when used as a normal FastAPI dependency."""
    _authorize_request(request)


class AuthenticatedAPIRoute(APIRoute):
    """Authenticate before FastAPI parses a potentially large multipart body."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        route_handler = super().get_route_handler()

        async def authenticated_handler(request: Request) -> Response:
            _authorize_request(request)
            return await route_handler(request)

        return authenticated_handler
