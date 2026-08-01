from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.health import router as health_router
from app.api.routes.slice import router as slice_router
from app.api.dependencies import build_slicer_runtime
from app.config import settings

_SLICE_PATHS = frozenset({"/api/v1/slice", "/api/v1/slice-artifact"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_startup()
    app.state.slicer_runtime = build_slicer_runtime()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.service_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )

    app.include_router(health_router, prefix="/health")
    app.include_router(slice_router, prefix="/api/v1")

    @app.exception_handler(RequestValidationError)
    async def slicer_validation_error(request: Request, exc: RequestValidationError):
        if request.url.path not in _SLICE_PATHS:
            raise exc
        return _malformed_request_response()

    @app.exception_handler(StarletteHTTPException)
    async def slicer_http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path in _SLICE_PATHS and exc.status_code in {400, 413, 422}:
            if exc.status_code == 413:
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
            return _malformed_request_response()
        return await http_exception_handler(request, exc)

    return app


def _malformed_request_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "success": False,
            "error": {"code": "malformed_request", "message": "The slicer request is malformed."},
        },
    )


app = create_app()
