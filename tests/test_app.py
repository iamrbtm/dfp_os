from __future__ import annotations


def test_app_factory_creates_app(app):
    assert app is not None
    assert app.config["TESTING"] is True
    assert "sqlalchemy" in app.extensions
    assert "migrate" in app.extensions


def test_home_page_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Dude Fish OS" in response.data


def test_login_page_loads(client):
    response = client.get("/auth/login")

    assert response.status_code == 200
    assert b"Welcome back" in response.data


def test_dashboard_requires_login(client):
    response = client.get("/dashboard/")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_404_page_renders(client):
    response = client.get("/missing-page")

    assert response.status_code == 404
    assert b"We couldn\xe2\x80\x99t find that page." in response.data


def test_testing_config_overrides_apply(app, tmp_path):
    assert app.config["MAX_CONTENT_LENGTH_MB"] == 16
    assert app.config["UPLOAD_FOLDER"] == str(tmp_path / "uploads")
