from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    Category,
    InventoryLocation,
    PosSaleStatus,
    PosSessionStatus,
    Product,
    ProductStatus,
    ProductType,
    ProductVariant,
    User,
    UserRole,
)
from app.services.pos import close_session, get_session_summary, open_session, create_sale, void_session


def _ensure_admin(app):
    with app.app_context():
        u = User.query.filter_by(email="pos-admin@example.com").first()
        if not u:
            u = User(
                email="pos-admin@example.com",
                first_name="POS",
                last_name="Admin",
                role=UserRole.ADMIN,
                is_active=True,
            )
            u.set_password("secret")
            db.session.add(u)
            db.session.commit()
        return u


def _ensure_category():
    c = Category.query.filter_by(slug="pos-test-cat").first()
    if not c:
        c = Category(name="POS Test", slug="pos-test-cat", is_public=True, is_pos_visible=True)
        db.session.add(c)
        db.session.flush()
    return c


def _ensure_product(category):
    p = Product.query.filter_by(slug="pos-test-prod").first()
    if not p:
        p = Product(
            name="POS Test Product",
            slug="pos-test-prod",
            category_id=category.id,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            is_pos_visible=True,
            base_price=Decimal("10.00"),
        )
        db.session.add(p)
        db.session.flush()
    return p


def _ensure_variant(product):
    v = ProductVariant.query.filter_by(sku="POS-TEST-V1").first()
    if not v:
        v = ProductVariant(
            product_id=product.id, sku="POS-TEST-V1", name="Test V1", price=Decimal("10.00"), active=True
        )
        db.session.add(v)
        db.session.flush()
    return v


def _ensure_location():
    loc = InventoryLocation.query.filter_by(name="Test POS Bin").first()
    if not loc:
        loc = InventoryLocation(name="Test POS Bin", type="Bin", active=True)
        db.session.add(loc)
        db.session.flush()
    return loc


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


def _ensure_admin_id(app):
    with app.app_context():
        u = User.query.filter_by(email="pos-admin@example.com").first()
        if not u:
            u = User(
                email="pos-admin@example.com",
                first_name="POS",
                last_name="Admin",
                role=UserRole.ADMIN,
                is_active=True,
            )
            u.set_password("super-secret")
            db.session.add(u)
            db.session.commit()
        return u.id


def test_pos_open_session(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        loc = _ensure_location()
        s = open_session(
            user_id=admin_id,
            opening_cash=Decimal("50.00"),
            inventory_location_id=loc.id,
            notes="Test session",
        )
        assert s.status == PosSessionStatus.OPEN
        assert s.opening_cash == Decimal("50.00")
        assert s.session_number.startswith("POS-")


def test_pos_close_session(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        s = open_session(user_id=admin_id, opening_cash=Decimal("100.00"))
        closed = close_session(s.id, admin_id, Decimal("150.00"), notes="All done")
        assert closed.status == PosSessionStatus.CLOSED
        assert closed.closing_cash == Decimal("150.00")
        assert closed.closed_by_user_id == admin_id
        assert closed.closed_at is not None


def test_pos_close_session_not_open(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        s = open_session(user_id=admin_id, opening_cash=Decimal("100.00"))
        close_session(s.id, admin_id, Decimal("100.00"))
        import pytest
        with pytest.raises(ValueError, match="Session is not open"):
            close_session(s.id, admin_id, Decimal("200.00"))


def test_pos_void_session(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        s = open_session(user_id=admin_id, opening_cash=Decimal("0"))
        void_session(s.id)
        assert s.status == PosSessionStatus.VOIDED


def test_pos_create_sale(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        _ensure_category()
        prod = _ensure_product(_ensure_category())
        variant = _ensure_variant(prod)
        s = open_session(user_id=admin_id, opening_cash=Decimal("50.00"))
        sale, order = create_sale(
            session_id=s.id,
            payment_method="cash",
            amount_received=Decimal("20.00"),
            items=[
                {
                    "product_id": prod.id,
                    "variant_id": variant.id,
                    "quantity": 1,
                    "unit_price": "10.00",
                    "description": "Test Product",
                    "item_type": "product",
                },
            ],
        )
        assert sale.total == Decimal("10.00")
        assert sale.payment_method == "cash"
        assert sale.change_due == Decimal("10.00")
        assert order.source.value == "pos"
        assert order.total == Decimal("10.00")
        assert len(sale.items) == 1
        assert sale.status == PosSaleStatus.COMPLETED


def test_pos_create_sale_custom_item(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        s = open_session(user_id=admin_id, opening_cash=Decimal("0"))
        sale, order = create_sale(
            session_id=s.id,
            payment_method="venmo",
            amount_received=Decimal("25.00"),
            items=[
                {
                    "quantity": 1,
                    "unit_price": "25.00",
                    "description": "Custom keychain",
                    "item_type": "custom_item",
                },
            ],
        )
        assert sale.payment_method == "venmo"
        assert sale.total == Decimal("25.00")


def test_pos_create_sale_no_open_session(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        s = open_session(user_id=admin_id, opening_cash=Decimal("0"))
        close_session(s.id, admin_id, Decimal("0"))
        import pytest
        with pytest.raises(ValueError, match="Session is not open"):
            create_sale(s.id, "cash", Decimal("10"), [{"quantity": 1, "unit_price": "10", "description": "x"}])


def test_pos_get_session_summary(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        s = open_session(user_id=admin_id, opening_cash=Decimal("50.00"))
        summary = get_session_summary(s.id)
        assert summary["total_sales"] == Decimal("0")
        assert summary["sale_count"] == 0


def test_pos_get_session_summary_with_sales(app):
    with app.app_context():
        admin_id = _ensure_admin_id(app)
        s = open_session(user_id=admin_id, opening_cash=Decimal("50.00"))
        create_sale(s.id, "cash", Decimal("20"), [{"quantity": 1, "unit_price": "10", "description": "A"}])
        create_sale(s.id, "cash", Decimal("15"), [{"quantity": 1, "unit_price": "12", "description": "B"}])
        summary = get_session_summary(s.id)
        assert summary["sale_count"] == 2
        assert summary["total_sales"] == Decimal("22")
        assert summary["payment_totals"].get("cash") == Decimal("22")


# ---------------------------------------------------------------------------
# Admin blueprint tests
# ---------------------------------------------------------------------------


def test_pos_session_list_requires_login(client):
    response = client.get("/pos/sessions")
    assert response.status_code == 302


def test_pos_session_list_loads(client, login_admin):
    response = client.get("/pos/sessions", follow_redirects=True)
    assert response.status_code == 200


def test_pos_session_list_search(client, login_admin):
    response = client.get("/pos/sessions?q=test", follow_redirects=True)
    assert response.status_code == 200


def test_pos_session_new_form_loads(client, login_admin):
    response = client.get("/pos/sessions/new", follow_redirects=True)
    assert response.status_code == 200


def test_pos_session_new_create(client, login_admin):
    with client.application.app_context():
        loc = InventoryLocation(name="Market Bin", type="Bin", active=True)
        db.session.add(loc)
        db.session.commit()
        loc_id = loc.id
    response = client.post("/pos/sessions/new", data={
        "opening_cash": "75.00",
        "inventory_location_id": str(loc_id),
    }, follow_redirects=True)
    assert response.status_code == 200


def test_pos_session_index_redirect(client, login_admin):
    response = client.get("/pos/", follow_redirects=True)
    assert response.status_code == 200


def test_pos_session_detail_loads(client, login_admin):
    with client.application.app_context():
        admin = User.query.filter_by(email="owner@example.com").first()
        s = open_session(user_id=admin.id, opening_cash=Decimal("50.00"))
        sid = s.id
    response = client.get(f"/pos/sessions/{sid}", follow_redirects=True)
    assert response.status_code == 200


def test_pos_session_detail_not_found(client, login_admin):
    response = client.get("/pos/sessions/99999", follow_redirects=True)
    assert response.status_code == 200


def test_pos_session_close_form_loads(client, login_admin):
    with client.application.app_context():
        admin = User.query.filter_by(email="owner@example.com").first()
        s = open_session(user_id=admin.id, opening_cash=Decimal("50.00"))
        sid = s.id
    response = client.get(f"/pos/sessions/{sid}/close", follow_redirects=True)
    assert response.status_code == 200


def test_pos_session_close_submit(client, login_admin):
    with client.application.app_context():
        admin = User.query.filter_by(email="owner@example.com").first()
        s = open_session(user_id=admin.id, opening_cash=Decimal("50.00"))
        sid = s.id
    response = client.post(f"/pos/sessions/{sid}/close", data={
        "closing_cash": "50.00",
    }, follow_redirects=True)
    assert response.status_code == 200


def test_pos_session_void(client, login_admin):
    with client.application.app_context():
        admin = User.query.filter_by(email="owner@example.com").first()
        s = open_session(user_id=admin.id, opening_cash=Decimal("0"))
        sid = s.id
    response = client.post(f"/pos/sessions/{sid}/void", follow_redirects=True)
    assert response.status_code in (200, 302)


def test_pos_screen_loads(client, login_admin):
    with client.application.app_context():
        admin = User.query.filter_by(email="owner@example.com").first()
        s = open_session(user_id=admin.id, opening_cash=Decimal("0"))
        sid = s.id
    response = client.get(f"/pos/sessions/{sid}/screen", follow_redirects=True)
    assert response.status_code == 200


def test_pos_screen_no_session(client, login_admin):
    response = client.get("/pos/sessions/99999/screen", follow_redirects=True)
    assert response.status_code == 200


def test_pos_product_grid(client, login_admin):
    with client.application.app_context():
        admin = User.query.filter_by(email="owner@example.com").first()
        s = open_session(user_id=admin.id, opening_cash=Decimal("0"))
        sid = s.id
    response = client.get(f"/pos/sessions/{sid}/products", follow_redirects=True)
    assert response.status_code == 200


def test_pos_product_grid_filtered(client, login_admin):
    with client.application.app_context():
        admin = User.query.filter_by(email="owner@example.com").first()
        s = open_session(user_id=admin.id, opening_cash=Decimal("0"))
        sid = s.id
    response = client.get(f"/pos/sessions/{sid}/products?q=rainbow", follow_redirects=True)
    assert response.status_code == 200


def test_pos_checkout_json(app, client):
    with app.app_context():
        admin = User(
            email="checkout-admin@example.com",
            first_name="Checkout",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password("super-secret")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
        s = open_session(user_id=admin_id, opening_cash=Decimal("0"))
        sid = s.id

    resp = client.post("/auth/login", data={"email": "checkout-admin@example.com", "password": "super-secret"}, follow_redirects=True)
    assert resp.status_code == 200

    import json
    response = client.post(
        f"/pos/sessions/{sid}/checkout",
        data=json.dumps({
            "payment_method": "cash",
            "amount_received": "10.00",
            "items": [{"quantity": 1, "unit_price": "5.00", "description": "Test item"}],
        }),
        content_type="application/json",
    )
    assert response.status_code == 200, f"Got {response.status_code}: {response.data[:200]}"
    data = response.get_json()
    assert "redirect" in data


def test_pos_checkout_empty_cart(app, client):
    with app.app_context():
        admin = User(
            email="empty-cart@example.com",
            first_name="Empty",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password("super-secret")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
        s = open_session(user_id=admin_id, opening_cash=Decimal("0"))
        sid = s.id

    resp = client.post("/auth/login", data={"email": "empty-cart@example.com", "password": "super-secret"}, follow_redirects=True)
    assert resp.status_code == 200

    import json
    response = client.post(
        f"/pos/sessions/{sid}/checkout",
        data=json.dumps({"payment_method": "cash", "amount_received": "0", "items": []}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_pos_quick_customer(app, client):
    with app.app_context():
        admin = User(
            email="quick-admin@example.com",
            first_name="Quick",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password("super-secret")
        db.session.add(admin)
        db.session.commit()
    resp = client.post("/auth/login", data={"email": "quick-admin@example.com", "password": "super-secret"}, follow_redirects=True)
    assert resp.status_code == 200
    import json
    response = client.post(
        "/pos/customers/quick",
        data=json.dumps({"first_name": "Quick", "last_name": "Buyer"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["display_name"] == "Quick Buyer"


def test_pos_quick_customer_missing_name(app, client):
    with app.app_context():
        admin = User(
            email="quick2-admin@example.com",
            first_name="Quick2",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password("super-secret")
        db.session.add(admin)
        db.session.commit()
    resp = client.post("/auth/login", data={"email": "quick2-admin@example.com", "password": "super-secret"}, follow_redirects=True)
    assert resp.status_code == 200
    import json
    response = client.post(
        "/pos/customers/quick",
        data=json.dumps({"first_name": ""}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_pos_receipt_loads(app, client):
    with app.app_context():
        admin = User(
            email="receipt-admin@example.com",
            first_name="Receipt",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password("super-secret")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
        s = open_session(user_id=admin_id, opening_cash=Decimal("0"))
        sale, _ = create_sale(s.id, "cash", Decimal("10"), [{"quantity": 1, "unit_price": "5", "description": "X"}])
        sid, sale_id = s.id, sale.id

    resp = client.post("/auth/login", data={"email": "receipt-admin@example.com", "password": "super-secret"}, follow_redirects=True)
    assert resp.status_code == 200
    response = client.get(f"/pos/sessions/{sid}/receipt/{sale_id}", follow_redirects=True)
    assert response.status_code == 200


def test_pos_api_list_sessions(client, api_token):
    response = client.get("/api/v1/pos-sessions", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200


def test_pos_api_create_session(client, api_token):
    with client.application.app_context():
        admin = User.query.filter_by(email="api-owner@example.com").first()
        admin_id = admin.id
    response = client.post(
        "/api/v1/pos-sessions",
        json={"opened_by_user_id": admin_id, "opening_cash": "25.00"},
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert response.status_code == 201


def test_pos_api_list_sales(client, api_token):
    response = client.get("/api/v1/pos-sales", headers={"Authorization": f"Bearer {api_token}"})
    assert response.status_code == 200
