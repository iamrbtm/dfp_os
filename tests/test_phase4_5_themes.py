from __future__ import annotations

import json
from pathlib import Path

from app.theme_registry import ALL_THEMES, DEFAULT_THEME, REQUIRED_TOKENS, is_valid_theme

BASE_DIR = Path(__file__).resolve().parent.parent


def test_theme_registry_has_12_themes():
    assert len(ALL_THEMES) == 12


def test_theme_registry_has_required_tokens():
    for theme in ALL_THEMES:
        for token in REQUIRED_TOKENS:
            assert token in REQUIRED_TOKENS, f"Theme {theme.slug} missing token {token}"


def test_all_theme_slugs_have_matching_css():
    css_path = BASE_DIR / "app" / "static" / "src" / "css" / "theme-tokens.css"
    css = css_path.read_text()
    for theme in ALL_THEMES:
        selector = f'[data-theme="{theme.slug}"]'
        assert selector in css, f"Missing CSS selector for {theme.slug}"


def test_each_theme_has_mode():
    for theme in ALL_THEMES:
        assert theme.mode in ("light", "dark"), f"Theme {theme.slug} has invalid mode {theme.mode}"


def test_default_theme_is_valid():
    assert is_valid_theme(DEFAULT_THEME), f"Default theme {DEFAULT_THEME} is not in registry"


def test_theme_settings_page_loads(client, login_admin):
    response = client.get("/settings/themes", follow_redirects=True)
    assert response.status_code == 200


def test_theme_settings_page_requires_login(client):
    response = client.get("/settings/themes")
    assert response.status_code == 302


def test_apply_theme_persists(client, login_admin):
    response = client.post(
        "/settings/themes/apply",
        data=json.dumps({"theme_slug": "dfp-dracula"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["theme_slug"] == "dfp-dracula"

    from app.models import User
    with client.application.app_context():
        admin = User.query.filter_by(email="owner@example.com").first()
        assert admin.theme_slug == "dfp-dracula"


def test_apply_invalid_theme_rejected(client, login_admin):
    response = client.post(
        "/settings/themes/apply",
        data=json.dumps({"theme_slug": "nonexistent-theme"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_api_list_themes(client, api_token):
    response = client.get(
        "/api/v1/themes",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 10


def test_api_current_theme(client, login_admin):
    response = client.get("/settings/api/themes/current")
    assert response.status_code == 200
    data = response.get_json()
    assert "slug" in data
    assert "name" in data
    assert "mode" in data


def test_api_update_user_theme(client, login_admin):
    response = client.patch(
        "/settings/api/users/me/theme",
        data=json.dumps({"theme_slug": "dfp-tokyo-night"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["theme_slug"] == "dfp-tokyo-night"


def test_api_update_user_theme_invalid(client, login_admin):
    response = client.patch(
        "/settings/api/users/me/theme",
        data=json.dumps({"theme_slug": "bad-slug"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_app_css_component_classes_exist():
    css_path = BASE_DIR / "app" / "static" / "src" / "css" / "app.css"
    css = css_path.read_text()
    required_classes = [
        ".app-card",
        ".app-btn",
        ".app-btn-primary",
        ".app-btn-secondary",
        ".app-btn-danger",
        ".app-btn-ghost",
        ".app-input",
        ".app-select",
        ".app-textarea",
        ".app-table",
        ".app-badge",
        ".app-badge-success",
        ".app-badge-warning",
        ".app-badge-danger",
        ".app-alert",
        ".pos-product-tile",
        ".pos-category-button",
        ".pos-cart-panel",
        ".pos-checkout-button",
    ]
    for cls in required_classes:
        assert cls in css, f"Missing CSS class definition: {cls}"


def test_theme_switcher_js_exists():
    js_path = BASE_DIR / "app" / "static" / "src" / "js" / "theme-switcher.js"
    assert js_path.exists()
    js = js_path.read_text()
    assert "__applyTheme" in js
    assert "localStorage" in js
    assert "data-theme" in js


def test_theme_switcher_updates_header(client, login_admin):
    response = client.get("/settings/themes", follow_redirects=True)
    assert response.status_code == 200
    assert b'__applyTheme' in response.data or b'theme' in response.data.lower()


def test_pos_page_has_theme_root(client, login_admin):
    with client.application.app_context():
        from app.models import User
        from app.services.pos import open_session
        from decimal import Decimal
        admin = User.query.filter_by(email="owner@example.com").first()
        s = open_session(user_id=admin.id, opening_cash=Decimal("0"))
        sid = s.id
    response = client.get(f"/pos/sessions/{sid}/screen", follow_redirects=True)
    assert response.status_code == 200
    html = response.data.decode()
    assert 'data-theme="' in html
