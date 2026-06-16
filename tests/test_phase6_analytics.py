from __future__ import annotations

from decimal import Decimal

from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import (
    Category,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    Product,
    ProductStatus,
    ProductType,
    ProductVariant,
    User,
    UserRole,
)
from app.services.analytics import (
    executive_summary,
    expense_analytics,
    inventory_analytics,
    market_analytics,
    pos_analytics,
    printing_analytics,
    product_analytics,
)


def test_executive_summary_returns_expected_keys(app: Flask):
    with app.app_context():
        summary = executive_summary()
        assert "today_revenue" in summary
        assert "month_revenue" in summary
        assert "open_orders_count" in summary
        assert "open_custom_requests" in summary
        assert "print_jobs_queued" in summary
        assert "low_inventory_count" in summary
        assert "low_filament_count" in summary
        assert "upcoming_markets" in summary


def test_executive_summary_with_data(app: Flask):
    from datetime import datetime, timezone
    with app.app_context():
        order = Order(
            source=OrderSource.POS,
            status=OrderStatus.COMPLETED,
            total=Decimal("100"),
            paid_amount=Decimal("100"),
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(order)
        db.session.commit()

        summary = executive_summary()
        assert summary["month_revenue"] >= Decimal("100")

        db.session.delete(order)
        db.session.commit()


def test_product_analytics_returns_list(app: Flask):
    with app.app_context():
        results = product_analytics()
        assert isinstance(results, list)


def test_product_analytics_with_data(app: Flask):
    with app.app_context():
        cat = Category(name="Test Analytics Category", slug="test-analytics-cat", sort_order=1)
        db.session.add(cat)
        db.session.flush()

        product = Product(
            name="Test Analytics Product",
            slug="test-analytics-product",
            sku_base="TAP-001",
            category_id=cat.id,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            base_price=Decimal("25"),
        )
        db.session.add(product)
        db.session.flush()

        variant = ProductVariant(
            product_id=product.id,
            sku="TAP-001",
            name="Default",
            price=Decimal("25"),
            active=True,
        )
        db.session.add(variant)
        db.session.flush()

        from datetime import datetime, timezone
        order = Order(
            source=OrderSource.POS,
            status=OrderStatus.COMPLETED,
            total=Decimal("25"),
            paid_amount=Decimal("25"),
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(order)
        db.session.flush()

        item = OrderItem(order_id=order.id, product_id=product.id, variant_id=variant.id, quantity=1, unit_price=Decimal("25"), line_total=Decimal("25"))
        db.session.add(item)
        db.session.commit()

        results = product_analytics()
        names = [p["name"] for p in results]
        assert product.name in names


def test_market_analytics_returns_list(app: Flask):
    with app.app_context():
        results = market_analytics()
        assert isinstance(results, list)


def test_pos_analytics_returns_expected_keys(app: Flask):
    with app.app_context():
        result = pos_analytics(days=30)
        assert "total_revenue" in result
        assert "total_sales" in result
        assert "avg_ticket" in result
        assert "payment_totals" in result
        assert "sales_by_day" in result
        assert "open_sessions" in result


def test_printing_analytics_returns_expected_keys(app: Flask):
    with app.app_context():
        result = printing_analytics()
        assert "printers" in result
        assert "total_completed" in result
        assert "total_failures" in result
        assert "total_queued" in result
        assert "overall_failure_rate" in result


def test_inventory_analytics_returns_expected_keys(app: Flask):
    with app.app_context():
        result = inventory_analytics()
        assert "low_stock_count" in result
        assert "location_counts" in result
        assert "total_inventory_value" in result
        assert "filament_low" in result
        assert "filament_empty" in result


def test_expense_analytics_returns_expected_keys(app: Flask):
    with app.app_context():
        result = expense_analytics(months=6)
        assert "by_category" in result
        assert "monthly_trend" in result
        assert "total_expenses" in result
        assert "months" in result


def test_analytics_page_requires_login(client: FlaskClient):
    response = client.get("/analytics/", follow_redirects=True)
    assert response.status_code == 200
    assert "Sign in" in response.text


def test_analytics_page_loads_for_admin(app: Flask, client: FlaskClient):
    with app.app_context():
        admin = User(
            email="analytics-test@example.com",
            first_name="Analytics",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password("super-secret")
        db.session.add(admin)
        db.session.commit()

    client.post("/auth/login", data={"email": "analytics-test@example.com", "password": "super-secret"}, follow_redirects=True)
    response = client.get("/analytics/")
    assert response.status_code == 200
    assert "Analytics" in response.text
    assert "Executive" in response.text or "Today" in response.text or "Revenue" in response.text


def test_analytics_api_summary_requires_token(client: FlaskClient):
    response = client.get("/api/v1/analytics/summary")
    assert response.status_code in (401, 403)


def test_analytics_api_summary_with_token(app: Flask, client: FlaskClient):
    from app.models import ApiToken
    with app.app_context():
        admin = User(email="api-analytics@example.com", first_name="API", last_name="Analytics", role=UserRole.ADMIN, is_active=True)
        admin.set_password("pw")
        db.session.add(admin)
        db.session.flush()

        import hashlib
        raw = "test-analytics-token-abc123"
        token = ApiToken(
            user_id=admin.id,
            name="Test Analytics",
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            prefix=raw[:8],
        )
        db.session.add(token)
        db.session.commit()

    response = client.get("/api/v1/analytics/summary", headers={"Authorization": f"Bearer {raw}"})
    assert response.status_code == 200
    data = response.get_json()
    assert "today_revenue" in data
    assert "month_revenue" in data


def test_home_page_loads(client: FlaskClient):
    response = client.get("/")
    assert response.status_code == 200


def test_about_page_loads(client: FlaskClient):
    response = client.get("/about")
    assert response.status_code == 200
    assert "About" in response.text


def test_faq_page_loads(client: FlaskClient):
    response = client.get("/faq")
    assert response.status_code == 200
    assert "FAQ" in response.text or "Frequently" in response.text


def test_contact_page_loads(client: FlaskClient):
    response = client.get("/contact")
    assert response.status_code == 200
    assert "Contact" in response.text


def test_small_business_page_loads(client: FlaskClient):
    response = client.get("/small-business-products")
    assert response.status_code == 200
    assert "Business" in response.text


def test_military_family_gifts_page_loads(client: FlaskClient):
    response = client.get("/military-family-gifts")
    assert response.status_code == 200
    assert "Military" in response.text or "Gifts" in response.text


def test_market_schedule_page_loads(client: FlaskClient):
    response = client.get("/market-schedule")
    assert response.status_code == 200
    assert "Schedule" in response.text or "Market" in response.text


def test_privacy_page_loads(client: FlaskClient):
    response = client.get("/privacy")
    assert response.status_code == 200
    assert "Privacy" in response.text


def test_terms_page_loads(client: FlaskClient):
    response = client.get("/terms")
    assert response.status_code == 200
    assert "Terms" in response.text


def test_market_schedule_shows_markets(app: Flask, client: FlaskClient):
    from app.models import Market, MarketStatus
    with app.app_context():
        m = Market(name="Test Vendor Market", status=MarketStatus.SCHEDULED, location_name="Clarksville")
        db.session.add(m)
        db.session.commit()

    response = client.get("/market-schedule")
    assert response.status_code == 200
    assert "Test Vendor Market" in response.text


def test_dashboard_shows_real_data(app: Flask, client: FlaskClient):
    with app.app_context():
        admin = User(
            email="dash-test@example.com",
            first_name="Dash",
            last_name="Test",
            role=UserRole.ADMIN,
            is_active=True,
        )
        admin.set_password("super-secret")
        db.session.add(admin)
        db.session.commit()

        order = Order(source=OrderSource.POS, status=OrderStatus.COMPLETED, total=Decimal("50"), paid_amount=Decimal("50"))
        db.session.add(order)
        db.session.commit()

    client.post("/auth/login", data={"email": "dash-test@example.com", "password": "super-secret"}, follow_redirects=True)
    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert "Today" in response.text or "Month" in response.text
