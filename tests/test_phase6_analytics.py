from __future__ import annotations

from decimal import Decimal

from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import (
    ApiToken,
    Category,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    Product,
    ProductStatus,
    ProductType,
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


def test_product_analytics_with_product_only_order_data(app: Flask):
    with app.app_context():
        category = Category(name="Analytics", slug="analytics", sort_order=1)
        product = Product(
            name="Analytics Product",
            slug="analytics-product",
            sku_base="AN-001",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            base_price=Decimal("25.00"),
        )
        order = Order(
            source=OrderSource.POS,
            status=OrderStatus.COMPLETED,
            total=Decimal("25.00"),
            paid_amount=Decimal("25.00"),
        )
        db.session.add_all([category, product, order])
        db.session.flush()
        db.session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=1,
                unit_price=Decimal("25.00"),
                line_total=Decimal("25.00"),
            )
        )
        db.session.commit()

        results = product_analytics()
        assert product.name in [row["name"] for row in results]


def test_other_analytics_helpers_return_expected_shapes(app: Flask):
    with app.app_context():
        assert isinstance(market_analytics(), list)
        assert "total_revenue" in pos_analytics(days=30)
        assert "printers" in printing_analytics()
        assert "low_stock_count" in inventory_analytics()
        assert "by_category" in expense_analytics(months=6)


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


def test_analytics_api_summary_with_token(app: Flask, client: FlaskClient):
    import hashlib

    with app.app_context():
        admin = User(email="api-analytics@example.com", first_name="API", last_name="Analytics", role=UserRole.ADMIN, is_active=True)
        admin.set_password("pw")
        db.session.add(admin)
        db.session.flush()
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
