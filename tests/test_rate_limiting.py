from __future__ import annotations

from app.utils.rate_limit import reset_limits


def test_login_rate_limited(client, admin_user):
    reset_limits()
    client.application.config.update(
        RATE_LIMIT_ENABLED=True,
        LOGIN_RATE_LIMIT_ATTEMPTS=2,
        LOGIN_RATE_LIMIT_WINDOW_SECONDS=60,
    )

    for _ in range(2):
        response = client.post(
            "/auth/login",
            data={"email": admin_user["email"], "password": "bad-password-long-enough"},
        )
        assert response.status_code == 200

    response = client.post(
        "/auth/login",
        data={"email": admin_user["email"], "password": "bad-password-long-enough"},
    )

    assert response.status_code == 429


def test_api_auth_failures_rate_limited(client):
    reset_limits()
    client.application.config.update(
        RATE_LIMIT_ENABLED=True,
        API_AUTH_RATE_LIMIT_ATTEMPTS=2,
        API_AUTH_RATE_LIMIT_WINDOW_SECONDS=60,
    )

    for _ in range(2):
        response = client.get("/api/v1/products", headers={"Authorization": "Bearer bad"})
        assert response.status_code == 401

    response = client.get("/api/v1/products", headers={"Authorization": "Bearer bad"})

    assert response.status_code == 429
