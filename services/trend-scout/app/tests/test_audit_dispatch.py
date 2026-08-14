"""Tests for the audit dispatch helper.

Verifies the wrapper:
- is a no-op when AUDIT_LOG_ENABLED=false (returns False)
- hits the configured audit-log URL when enabled
- returns False on HTTP error (never raises)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings as app_settings
from app.services import audit_dispatch


@pytest.mark.asyncio
async def test_dispatch_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "audit_log_enabled", False)
    ok = await audit_dispatch.dispatch_audit_event(
        action="trend_scout.test.skipped",
        entity_type="test",
        entity_id="1",
    )
    assert ok is False


@pytest.mark.asyncio
async def test_dispatch_posts_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "audit_log_enabled", True)
    monkeypatch.setattr(app_settings, "audit_log_base_url", "http://audit:8090")
    monkeypatch.setattr(app_settings, "audit_log_token", "test-token")

    fake_response = MagicMock()
    fake_response.status_code = 201

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.post = AsyncMock(return_value=fake_response)

    with patch("httpx.AsyncClient", return_value=fake_client):
        ok = await audit_dispatch.dispatch_audit_event(
            action="trend_scout.test.dispatched",
            entity_type="test",
            entity_id="1",
        )
    assert ok is True
    fake_client.post.assert_awaited_once()
    args, kwargs = fake_client.post.call_args
    assert args[0].endswith("/api/v1/audit-events")
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert kwargs["json"]["action"] == "trend_scout.test.dispatched"


@pytest.mark.asyncio
async def test_dispatch_returns_false_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "audit_log_enabled", True)
    monkeypatch.setattr(app_settings, "audit_log_base_url", "http://audit:8090")
    monkeypatch.setattr(app_settings, "audit_log_token", "test-token")

    fake_response = MagicMock()
    fake_response.status_code = 500

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.post = AsyncMock(return_value=fake_response)

    with patch("httpx.AsyncClient", return_value=fake_client):
        ok = await audit_dispatch.dispatch_audit_event(
            action="trend_scout.test.error",
            entity_type="test",
            entity_id="1",
        )
    assert ok is False


@pytest.mark.asyncio
async def test_dispatch_returns_false_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "audit_log_enabled", True)

    with patch("httpx.AsyncClient", side_effect=RuntimeError("boom")):
        ok = await audit_dispatch.dispatch_audit_event(
            action="trend_scout.test.exception",
            entity_type="test",
            entity_id="1",
        )
    assert ok is False
