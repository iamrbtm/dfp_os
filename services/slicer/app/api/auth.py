from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status
from fastapi.routing import APIRoute
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.responses import JSONResponse, Response
from starlette.types import Message, Receive

from app.config import is_valid_internal_api_token, settings

MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_MULTIPART_FIELDS = 4
MAX_MULTIPART_FIELD_BYTES = 16 * 1024
MAX_MULTIPART_HEADER_BYTES = 4 * 1024
MAX_MULTIPART_TOTAL_HEADER_BYTES = 16 * 1024

_LOGGER = logging.getLogger(__name__)


class RequestBodyTooLarge(Exception):
    pass


class TooManyMultipartParts(Exception):
    pass


class MalformedMultipart(Exception):
    pass


class MultipartHeadersTooLarge(Exception):
    pass


class _TooManyFields(MultiPartException):
    pass


class _InvalidFilePart(MultiPartException):
    pass


class _OversizedField(MultiPartException):
    pass


class _OversizedHeaders(MultiPartException):
    pass


class _SliceMultipartParser(MultiPartParser):
    """Streaming parser that rejects unapproved file parts before creating their spool."""

    def on_part_begin(self) -> None:
        self._current_header_bytes = 0
        super().on_part_begin()

    def _track_header_bytes(self, start: int, end: int) -> None:
        chunk_bytes = end - start
        self._current_header_bytes += chunk_bytes
        self._total_header_bytes = getattr(self, "_total_header_bytes", 0) + chunk_bytes
        if (
            self._current_header_bytes > MAX_MULTIPART_HEADER_BYTES
            or self._total_header_bytes > MAX_MULTIPART_TOTAL_HEADER_BYTES
        ):
            raise _OversizedHeaders("Multipart part headers exceed the configured limit.")

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._track_header_bytes(start, end)
        super().on_header_field(data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._track_header_bytes(start, end)
        super().on_header_value(data, start, end)

    def on_headers_finished(self) -> None:
        _disposition, options = parse_options_header(self._current_part.content_disposition)
        raw_name = options.get(b"name")
        if raw_name is None:
            raise _InvalidFilePart('The Content-Disposition header field "name" must be provided.')
        charset = self._charset or "utf-8"
        try:
            field_name = raw_name.decode(charset, errors="replace")
        except LookupError:
            field_name = raw_name.decode("latin-1")
        if b"filename" in options:
            if field_name != "model_file" or self._current_files >= 1:
                raise _InvalidFilePart("Exactly one model_file upload is allowed.")
        elif self._current_fields >= MAX_MULTIPART_FIELDS:
            raise _TooManyFields(f"Too many fields. Maximum number of fields is {MAX_MULTIPART_FIELDS}.")
        super().on_headers_finished()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is None and len(self._current_part.data) + end - start > self.max_part_size:
            raise _OversizedField("Multipart field data exceeds the configured limit.")
        super().on_part_data(data, start, end)

    async def parse(self) -> FormData:
        try:
            return await super().parse()
        except BaseException:
            self.close_owned_files()
            raise

    def close_owned_files(self) -> None:
        for spool in self._files_to_close_on_error:
            try:
                spool.close()
            except OSError:
                _LOGGER.warning("A multipart temporary file could not be closed.")


async def preparse_slice_multipart(request: Request) -> FormData:
    """Parse a bounded slice form once so FastAPI reuses the validated result."""
    parser = _SliceMultipartParser(
        request.headers,
        request.stream(),
        max_files=1,
        max_fields=MAX_MULTIPART_FIELDS,
        max_part_size=MAX_MULTIPART_FIELD_BYTES,
    )
    try:
        form = await parser.parse()
    except (_TooManyFields, _OversizedField) as exc:
        raise TooManyMultipartParts from exc
    except _OversizedHeaders as exc:
        raise MultipartHeadersTooLarge from exc
    except _InvalidFilePart as exc:
        raise MalformedMultipart from exc
    except (MultiPartException, MultipartParseError) as exc:
        raise MalformedMultipart from exc

    file_parts = [(name, value) for name, value in form.multi_items() if isinstance(value, UploadFile)]
    if len(file_parts) != 1 or file_parts[0][0] != "model_file":
        parser.close_owned_files()
        raise MalformedMultipart
    request._form = form
    return form


async def _close_form_files(form: FormData) -> None:
    cancellation: asyncio.CancelledError | None = None
    for _name, value in form.multi_items():
        if isinstance(value, UploadFile):
            try:
                await value.close()
            except asyncio.CancelledError as exc:
                cancellation = cancellation or exc
            except Exception:
                _LOGGER.warning("A cached multipart upload could not be closed.")
    if cancellation is not None:
        raise cancellation


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


def _too_many_parts_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        content={
            "success": False,
            "error": {
                "code": "too_many_parts",
                "message": "The multipart request contains too many fields or oversized field data.",
            },
        },
    )


def _multipart_headers_too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        content={
            "success": False,
            "error": {
                "code": "multipart_headers_too_large",
                "message": "A multipart part contains too much header data.",
            },
        },
    )


def _malformed_request_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "success": False,
            "error": {"code": "malformed_request", "message": "The slicer request is malformed."},
        },
    )


def _parse_failed_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "success": False,
            "error": {
                "code": "request_parse_failed",
                "message": "The slicer request could not be processed.",
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
                try:
                    await preparse_slice_multipart(request)
                except RequestBodyTooLarge:
                    return _request_too_large_response()
                except TooManyMultipartParts:
                    return _too_many_parts_response()
                except MultipartHeadersTooLarge:
                    return _multipart_headers_too_large_response()
                except MalformedMultipart:
                    return _malformed_request_response()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    _LOGGER.exception("Multipart request parsing failed.")
                    return _parse_failed_response()
                return await route_handler(request)
            finally:
                cached_form = getattr(request, "_form", None)
                if isinstance(cached_form, FormData):
                    await _close_form_files(cached_form)

        return authenticated_handler
