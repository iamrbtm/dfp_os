from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import audit_events, health
from app.config import settings
from app.telemetry import setup_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry(settings.service_name)
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

    app.include_router(health.router, prefix="/health")
    app.include_router(audit_events.router)

    return app


app = create_app()
