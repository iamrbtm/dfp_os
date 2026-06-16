from app.extensions import db
from app.models import ApiToken, User, UserRole
from app.services.api_tokens import create_api_token


def _make_user_and_token(client):
    with client.application.app_context():
        user = User(
            email="token-owner@example.com",
            first_name="Token",
            last_name="Owner",
            role=UserRole.STAFF,
            is_active=True,
        )
        user.set_password("super-secret")
        db.session.add(user)
        db.session.commit()
        uid = user.id
    return uid


def _login(client):
    client.post("/auth/login", data={"email": "token-owner@example.com", "password": "super-secret"})


def _make_token(client, name="Test Token", user_id=None):
    with client.application.app_context():
        if user_id is None:
            users = User.query.all()
            user = users[0] if users else User(
                email="fallback@example.com", first_name="F", last_name="B",
                role=UserRole.STAFF, is_active=True,
            )
        else:
            user = db.session.get(User, user_id)
        token, raw = create_api_token(user=user, name=name)
        tid = token.id
    return tid, raw


def test_create_api_token_via_service(app):
    with app.app_context():
        user = User(
            email="svc@example.com", first_name="Svc", last_name="User",
            role=UserRole.STAFF, is_active=True,
        )
        user.set_password("pw")
        db.session.add(user)
        db.session.commit()
        token, raw = create_api_token(user=user, name="Test Token")
        assert token.name == "Test Token"
        assert token.prefix == raw[:8]
        assert token.is_active
        assert token.user_id == user.id


def test_create_api_token_with_expiry(app):
    with app.app_context():
        user = User(
            email="exp@example.com", first_name="Exp", last_name="User",
            role=UserRole.STAFF, is_active=True,
        )
        user.set_password("pw")
        db.session.add(user)
        db.session.commit()
        from datetime import datetime, timezone, timedelta
        expires = datetime.now(timezone.utc) + timedelta(days=30)
        token, raw = create_api_token(user=user, name="Expiring", expires_at=expires)
        assert token.is_active


def test_create_api_token_with_scopes(app):
    with app.app_context():
        user = User(
            email="scope@example.com", first_name="S", last_name="U",
            role=UserRole.STAFF, is_active=True,
        )
        user.set_password("pw")
        db.session.add(user)
        db.session.commit()
        token, raw = create_api_token(user=user, name="Scoped", scopes=["read", "write"])
        assert token.scopes == "read,write"


def test_revoke_api_token(app):
    with app.app_context():
        user = User(
            email="rev@example.com", first_name="R", last_name="U",
            role=UserRole.STAFF, is_active=True,
        )
        user.set_password("pw")
        db.session.add(user)
        db.session.commit()
        token, raw = create_api_token(user=user, name="Revocable")
        assert token.is_active
        from app.models.base import utc_now
        token.revoked_at = utc_now()
        db.session.commit()
        assert not token.is_active


def test_api_token_list_page_requires_auth(client):
    response = client.get("/settings/api-tokens/", follow_redirects=True)
    assert response.status_code == 200
    assert b"Sign In" in response.data or b"login" in response.data


def test_api_token_list_page_logged_in(client):
    _make_user_and_token(client)
    _login(client)
    response = client.get("/settings/api-tokens/")
    assert response.status_code == 200
    assert b"API Tokens" in response.data


def test_api_token_create_page_logged_in(client):
    _make_user_and_token(client)
    _login(client)
    response = client.get("/settings/api-tokens/new")
    assert response.status_code == 200
    assert b"Create API Token" in response.data


def test_api_token_create_post(client):
    _make_user_and_token(client)
    _login(client)
    response = client.post("/settings/api-tokens/new", data={"name": "New Token"})
    assert response.status_code == 200
    assert b"Copy this token" in response.data


def test_api_token_create_requires_name(client):
    _make_user_and_token(client)
    _login(client)
    response = client.post("/settings/api-tokens/new", data={"name": ""})
    assert response.status_code == 200
    assert b"Token name is required" in response.data


def test_api_token_detail_page(client):
    uid = _make_user_and_token(client)
    _login(client)
    token_id, raw = _make_token(client, name="Detail Token", user_id=uid)
    response = client.get(f"/settings/api-tokens/{token_id}")
    assert response.status_code == 200
    assert b"Detail Token" in response.data


def test_api_token_revoke(client):
    uid = _make_user_and_token(client)
    _login(client)
    token_id, raw = _make_token(client, name="Revoke Me", user_id=uid)
    with client.application.app_context():
        token = db.session.get(ApiToken, token_id)
        assert token.is_active
    response = client.post(f"/settings/api-tokens/{token_id}/revoke")
    assert response.status_code == 302
    with client.application.app_context():
        token = db.session.get(ApiToken, token_id)
        assert not token.is_active


def test_api_v1_create_token_endpoint(api_token, client):
    response = client.post(
        "/api/v1/api-tokens",
        json={"name": "API Created Token"},
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["data"]["name"] == "API Created Token"
    assert "raw_token" in data["data"]
    assert data["data"]["is_active"]


def test_api_v1_list_tokens(api_token, client):
    response = client.get("/api/v1/api-tokens", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data["data"], list)


def test_api_v1_get_token(api_token, client):
    with client.application.app_context():
        user = db.session.get(User, 1)
        token, raw = create_api_token(user=user, name="Getable")
        tid = token.id
    response = client.get(f"/api/v1/api-tokens/{tid}", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "Getable"


def test_api_v1_delete_token(api_token, client):
    with client.application.app_context():
        user = db.session.get(User, 1)
        token, raw = create_api_token(user=user, name="Deletable")
        tid = token.id
    response = client.delete(f"/api/v1/api-tokens/{tid}", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200
    assert response.get_json()["status"] == "revoked"
    with client.application.app_context():
        token = db.session.get(ApiToken, tid)
        assert not token.is_active


def test_api_v1_create_token_requires_name(api_token, client):
    response = client.post("/api/v1/api-tokens", json={"name": ""}, headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 400


def test_api_v1_token_not_found(api_token, client):
    response = client.get("/api/v1/api-tokens/99999", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 404


def test_api_v1_token_requires_auth(client):
    response = client.get("/api/v1/api-tokens")
    assert response.status_code == 401
