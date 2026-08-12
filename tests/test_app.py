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
    assert b"couldn" in response.data and b"find that page" in response.data


def test_testing_config_overrides_apply(app, tmp_path):
    assert app.config["MAX_CONTENT_LENGTH_MB"] == 16
    assert app.config["UPLOAD_FOLDER"] == str(tmp_path / "uploads")


def test_authenticated_sidebar_uses_grouped_navigation(client, login_admin):
    response = client.get("/dashboard/")

    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Quick access" in html
    assert "Sell" in html
    assert "Make" in html
    assert "Stock" in html
    assert "Money" in html
    assert "Grow" in html
    assert "System" in html
    assert "Dashboard" in html
    assert "Notifications" in html
    assert "POS" in html
    assert "Categories" in html
    assert "Collections" in html
    assert "Feature Flags" in html
    assert "Booth Mode" in html
    assert "Table Layouts" in html
    assert "Display Signs" in html
    assert "Heat Map" in html
    assert "Task Monitor" in html


def test_active_sidebar_group_expands_for_product_pages(client, login_admin):
    response = client.get("/products/studio")

    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'x-data="{ open: true }"' in html
    assert "Make" in html
    assert "Categories" in html
    assert "Collections" in html
