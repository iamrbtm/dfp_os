from uuid import uuid4

from app.extensions import db
from app.models import ApiToken, User, UserRole
from app.services.api_tokens import create_api_token, revoke_api_token
from app.utils.rate_limit import reset_limits


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


def _login(client, expected_user_id=None):
    reset_limits()
    response = client.post(
        "/auth/login",
        data={"email": "token-owner@example.com", "password": "super-secret"},
    )
    assert response.status_code == 302
    if expected_user_id is not None:
        with client.session_transaction() as session:
            assert session.get("_user_id") == str(expected_user_id)


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


def _make_token_for_owner(client, name="Test Token"):
    with client.application.app_context():
        user = User.query.filter_by(email="token-owner@example.com").first()
        token, raw = create_api_token(user=user, name=name)
        assert token.user_id == user.id
        return token.id, raw


def _make_api_token(client, scopes=None, *, active_user=True):
    with client.application.app_context():
        suffix = uuid4().hex
        user = User(
            email=f"api-{suffix}@example.com",
            first_name="API",
            last_name="User",
            role=UserRole.ADMIN,
            is_active=active_user,
        )
        user.set_password("super-secret")
        db.session.add(user)
        db.session.commit()
        token, raw = create_api_token(user=user, name="API Test Token", scopes=scopes)
        return token.id, raw


def _auth_header(raw_token):
    return {"Authorization": f"Bearer {raw_token}"}


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
        assert not token.has_scope("catalog")


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
        revoke_api_token(token, actor_id=user.id)
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
    assert b'name="csrf_token"' in response.data
    assert b'value="catalog"' in response.data


def test_api_token_create_post(client):
    _make_user_and_token(client)
    _login(client)
    response = client.post("/settings/api-tokens/new", data={"name": "New Token"})
    assert response.status_code == 200
    assert b"Copy this token" in response.data


def test_api_token_create_post_with_checkbox_scopes(client):
    _make_user_and_token(client)
    _login(client)
    response = client.post(
        "/settings/api-tokens/new",
        data={"name": "Scoped Token", "scopes": ["catalog", "analytics"]},
    )
    assert response.status_code == 200
    with client.application.app_context():
        token = ApiToken.query.filter_by(name="Scoped Token").first()
        assert token.scopes == "catalog,analytics"


def test_api_token_create_requires_name(client):
    _make_user_and_token(client)
    _login(client)
    response = client.post("/settings/api-tokens/new", data={"name": ""})
    assert response.status_code == 200
    assert b"Token name is required" in response.data


def test_api_token_detail_page(client):
    uid = _make_user_and_token(client)
    _login(client, uid)
    response = client.post("/settings/api-tokens/new", data={"name": "Detail Token"})
    assert response.status_code == 200
    with client.application.app_context():
        token_id = ApiToken.query.filter_by(name="Detail Token").one().id
    response = client.get(f"/settings/api-tokens/{token_id}")
    assert response.status_code == 200
    assert b"Detail Token" in response.data


def test_api_token_revoke(client):
    uid = _make_user_and_token(client)
    _login(client, uid)
    response = client.post("/settings/api-tokens/new", data={"name": "Revoke Me"})
    assert response.status_code == 200
    with client.application.app_context():
        token = ApiToken.query.filter_by(name="Revoke Me").one()
        token_id = token.id
        assert token.is_active
    response = client.post(f"/settings/api-tokens/{token_id}/revoke")
    assert response.status_code == 302, response.location
    with client.application.app_context():
        token = db.session.get(ApiToken, token_id)
        assert not token.is_active


def test_empty_scope_api_token_has_no_api_access(client):
    _token_id, raw = _make_api_token(client, scopes=[])
    response = client.get("/api/v1/products", headers=_auth_header(raw))
    assert response.status_code == 403


def test_deactivated_user_api_token_is_rejected(client):
    _token_id, raw = _make_api_token(client, scopes=["catalog"], active_user=False)
    response = client.get("/api/v1/products", headers=_auth_header(raw))
    assert response.status_code == 401


def test_scoped_token_cannot_create_api_tokens(client):
    _token_id, raw = _make_api_token(client, scopes=["settings"])
    response = client.post(
        "/api/v1/api-tokens",
        json={"name": "Escalated Token", "scopes": "admin"},
        headers=_auth_header(raw),
    )
    assert response.status_code == 403


def test_api_v1_create_token_endpoint(client):
    _token_id, raw = _make_api_token(client, scopes=["admin"])
    response = client.post(
        "/api/v1/api-tokens",
        json={"name": "API Created Token"},
        headers=_auth_header(raw),
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["data"]["name"] == "API Created Token"
    assert "raw_token" in data["data"]
    assert data["data"]["is_active"]


def test_api_v1_list_tokens(client):
    _token_id, raw = _make_api_token(client, scopes=["settings"])
    response = client.get("/api/v1/api-tokens", headers=_auth_header(raw))
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data["data"], list)


def test_api_v1_get_token(client):
    _token_id, auth_raw = _make_api_token(client, scopes=["settings"])
    with client.application.app_context():
        user = db.session.get(User, 1)
        token, raw = create_api_token(user=user, name="Getable")
        tid = token.id
    response = client.get(f"/api/v1/api-tokens/{tid}", headers=_auth_header(auth_raw))
    assert response.status_code == 200
    assert response.get_json()["data"]["name"] == "Getable"


def test_api_v1_delete_token(client):
    _token_id, auth_raw = _make_api_token(client, scopes=["settings"])
    with client.application.app_context():
        user = db.session.get(User, 1)
        token, raw = create_api_token(user=user, name="Deletable")
        tid = token.id
    response = client.delete(f"/api/v1/api-tokens/{tid}", headers=_auth_header(auth_raw))
    assert response.status_code == 200
    assert response.get_json()["status"] == "revoked"
    with client.application.app_context():
        token = db.session.get(ApiToken, tid)
        assert not token.is_active


def test_api_v1_create_token_requires_name(client):
    _token_id, raw = _make_api_token(client, scopes=["admin"])
    response = client.post("/api/v1/api-tokens", json={"name": ""}, headers=_auth_header(raw))
    assert response.status_code == 400


def test_api_v1_token_not_found(client):
    _token_id, raw = _make_api_token(client, scopes=["settings"])
    response = client.get("/api/v1/api-tokens/99999", headers=_auth_header(raw))
    assert response.status_code == 404


def test_api_v1_token_requires_auth(client):
    response = client.get("/api/v1/api-tokens")
    assert response.status_code == 401
