from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse, Response
from starlette.types import Message, Receive

from app.config import is_valid_internal_api_token, settings

MULTIPART_OVERHEAD_BYTES = 64 * 1024


class RequestBodyTooLarge(Exception):
    pass


def bounded_receive(receive: Receive, *, limit: int) -> Receive:
    received = 0

    async def receive_with_limit() -> Message:
        nonlocal received
        message = await receive()
        if message.get("type") == "http.request":
            body = message.get("body", b"")
            received += len(body) if isinstance(body, bytes) else 0
            if received > limit:
                raise RequestBodyTooLarge
        return message

    return receive_with_limit


def _request_too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        content={
            "success": False,
            "error": {
                "code": "request_too_large",
                "message": "The multipart request exceeds the configured upload limit.",
            },
        },
    )


def _authorize_request(request: Request) -> None:
    scheme, separator, provided_token = request.headers.get("Authorization", "").partition(" ")
    valid_scheme = bool(separator) and scheme.lower() == "bearer"
    configured_token = settings.internal_api_token
    valid_token = False
    if is_valid_internal_api_token(configured_token) and is_valid_internal_api_token(provided_token):
        valid_token = secrets.compare_digest(provided_token, configured_token)
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
            request_limit = settings.max_model_bytes + MULTIPART_OVERHEAD_BYTES
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_bytes = int(content_length)
                except ValueError:
                    declared_bytes = -1
                if declared_bytes < 0:
                    return JSONResponse(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        content={
                            "success": False,
                            "error": {"code": "malformed_request", "message": "The slicer request is malformed."},
                        },
                    )
                if declared_bytes > request_limit:
                    return _request_too_large_response()

            request._receive = bounded_receive(request.receive, limit=request_limit)
            try:
                return await route_handler(request)
            except RequestBodyTooLarge:
                return _request_too_large_response()

        return authenticated_handler
