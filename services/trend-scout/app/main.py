from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import (
    backtest,
    health,
    opportunities,
    pipeline,
    reports,
    settings,
    source_health,
    weights,
)
from app.config import settings as app_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=app_settings.service_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.include_router(health.router, prefix="/health")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(opportunities.router, prefix="/api/v1")
    app.include_router(source_health.router, prefix="/api/v1")
    app.include_router(weights.router, prefix="/api/v1")
    app.include_router(pipeline.router, prefix="/api/v1")
    app.include_router(backtest.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")
    return app


app = create_app()
