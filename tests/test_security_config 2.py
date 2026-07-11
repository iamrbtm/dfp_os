from __future__ import annotations

import pytest

from app import create_app


def test_production_rejects_default_secret(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "change-me")
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-admin-password")

    with pytest.raises(RuntimeError, match="Production SECRET_KEY"):
        create_app("production")


def test_security_headers_present(client):
    response = client.get("/")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in response.headers["Permissions-Policy"]
