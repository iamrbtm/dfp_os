from app.services.settings import (
    DEFAULT_SETTINGS,
    get_all_settings,
    get_setting,
    get_setting_typed,
    seed_default_settings,
    set_setting,
)


def test_seed_default_settings(app):
    with app.app_context():
        count = seed_default_settings()
        assert count == len(DEFAULT_SETTINGS)
        stored = get_setting("store_name")
        assert stored == "Dude Fish Printing"


def test_seed_is_idempotent(app):
    with app.app_context():
        seed_default_settings()
        count2 = seed_default_settings()
        assert count2 == 0


def test_get_setting_returns_default(app):
    with app.app_context():
        val = get_setting("nonexistent", "fallback")
        assert val == "fallback"


def test_set_setting_creates(app):
    with app.app_context():
        s = set_setting("test_key", "test_value", "A test setting")
        assert s.key == "test_key"
        assert s.value == "test_value"
        assert s.description == "A test setting"


def test_set_setting_updates(app):
    with app.app_context():
        set_setting("update_key", "old_value")
        set_setting("update_key", "new_value")
        assert get_setting("update_key") == "new_value"


def test_get_all_settings(app):
    with app.app_context():
        seed_default_settings()
        all_s = get_all_settings()
        assert len(all_s) >= len(DEFAULT_SETTINGS)


def test_get_setting_typed_string(app):
    with app.app_context():
        set_setting("test_str", "hello", type="string")
        assert get_setting_typed("test_str") == "hello"


def test_get_setting_typed_boolean(app):
    with app.app_context():
        set_setting("test_bool", "true", type="boolean")
        assert get_setting_typed("test_bool") is True
        set_setting("test_bool2", "false", type="boolean")
        assert get_setting_typed("test_bool2") is False


def test_get_setting_typed_integer(app):
    with app.app_context():
        set_setting("test_int", "42", type="integer")
        assert get_setting_typed("test_int") == 42


def test_settings_admin_page_requires_auth(client):
    response = client.get("/settings/", follow_redirects=True)
    assert b"Sign In" in response.data or b"login" in response.data


def test_settings_admin_page_logged_in(login_admin, client):
    with client.application.app_context():
        seed_default_settings()
    response = client.get("/settings/")
    assert response.status_code == 200
    assert b"Store" in response.data
    assert b"Dude Fish Printing" in response.data


def test_settings_admin_update(login_admin, client):
    with client.application.app_context():
        seed_default_settings()
    response = client.post("/settings/update", data={"store_name": "New Store Name"})
    assert response.status_code == 302
    with client.application.app_context():
        assert get_setting("store_name") == "New Store Name"


def test_api_v1_settings_list(api_token, client):
    with client.application.app_context():
        seed_default_settings()
    response = client.get("/api/v1/settings", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data["data"], list)
    keys = [s["key"] for s in data["data"]]
    assert "store_name" in keys


def test_api_v1_settings_get(api_token, client):
    with client.application.app_context():
        set_setting("test_api_key", "api_value")
    response = client.get("/api/v1/settings/test_api_key", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200
    assert response.get_json()["data"]["value"] == "api_value"


def test_api_v1_settings_get_not_found(api_token, client):
    response = client.get("/api/v1/settings/does-not-exist", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 404


def test_api_v1_settings_update(api_token, client):
    with client.application.app_context():
        set_setting("api_update_key", "old")
    response = client.put(
        "/api/v1/settings/api_update_key",
        json={"value": "new"},
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert response.status_code == 200
    with client.application.app_context():
        assert get_setting("api_update_key") == "new"


def test_api_v1_settings_update_requires_value(api_token, client):
    response = client.put(
        "/api/v1/settings/some-key",
        json={},
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert response.status_code == 400


def test_api_v1_settings_requires_token(client):
    response = client.get("/api/v1/settings")
    assert response.status_code == 401
