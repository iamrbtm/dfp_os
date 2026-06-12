from __future__ import annotations

from app.models import User, UserRole


def test_admin_user_can_log_in(client, admin_user):
    response = client.post(
        "/auth/login",
        data={
            "email": admin_user["email"],
            "password": admin_user["password"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Phase 1 control center" in response.data


def test_logout_clears_session(client, admin_user):
    client.post(
        "/auth/login",
        data={
            "email": admin_user["email"],
            "password": admin_user["password"],
        },
    )

    response = client.post("/auth/logout", follow_redirects=True)

    assert response.status_code == 200
    assert b"You\xe2\x80\x99ve been signed out." in response.data


def test_password_is_hashed(app):
    with app.app_context():
        user = User(
            email="hash-check@example.com",
            first_name="Hash",
            last_name="Check",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("plain-text-password")

        assert user.password_hash != "plain-text-password"
        assert user.check_password("plain-text-password") is True
