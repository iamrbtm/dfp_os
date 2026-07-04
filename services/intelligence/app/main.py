from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import advisor, health, imports, knowledge, legacy_review_gui, mappings, warehouse
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    app.include_router(imports.router, prefix="/api/v1")
    app.include_router(mappings.router, prefix="/api/v1")
    app.include_router(warehouse.router, prefix="/api/v1")
    app.include_router(advisor.router, prefix="/api/v1")
    app.include_router(knowledge.router, prefix="/api/v1")
    app.include_router(legacy_review_gui.router)
    return app


app = create_app()
