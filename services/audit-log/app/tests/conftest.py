import os

os.environ["AUDIT_DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///")
os.environ["AUDIT_LOG_LEVEL"] = "CRITICAL"

from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import Base, async_session_factory, engine
from app.main import create_app


@pytest.fixture(autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture()
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.internal_api_token}"}


@pytest.fixture()
def sample_event() -> dict:
    return {
        "occurred_at": "2026-06-15T10:00:00Z",
        "actor_id": "user-123",
        "actor_type": "user",
        "action": "test.action",
        "entity_type": "test_entity",
        "entity_id": "entity-123",
        "source_service": "test-service",
        "source_module": "test-module",
    }
