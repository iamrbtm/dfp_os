from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from app.security import verify_internal_token


@pytest.mark.asyncio
async def test_bearer_token_is_required(monkeypatch):
    monkeypatch.setattr("app.security.settings.internal_api_token", "secret")

    with pytest.raises(HTTPException) as exc:
        await verify_internal_token(authorization=None)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_bearer_token_is_accepted(monkeypatch):
    monkeypatch.setattr("app.security.settings.internal_api_token", "secret")

    assert await verify_internal_token(authorization="Bearer secret") is None


def test_query_token_parameter_is_not_supported():
    signature = inspect.signature(verify_internal_token)

    assert "token" not in signature.parameters
