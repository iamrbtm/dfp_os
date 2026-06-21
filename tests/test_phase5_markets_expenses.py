from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import (
    Category,
    Expense,
    ExpenseCategory,
    Market,
    MarketPackingList,
    MarketStatus,
    Product,
    ProductStatus,
    ProductType,
)


def test_market_model_can_be_created(app):
    with app.app_context():
        market = Market(
            name="Test Market",
            location_name="Test Location",
            city="Clarksville",
            state="TN",
            event_date=date(2026, 7, 1),
            booth_fee=Decimal("50.00"),
            status=MarketStatus.SCHEDULED,
        )
        db.session.add(market)
        db.session.commit()

        assert market.id is not None
        assert market.name == "Test Market"
        assert market.status == MarketStatus.SCHEDULED
        assert market.total_booth_cost == Decimal("50.00")
        assert market.profit_margin_pct is None


def test_expense_model_can_be_created(app):
    with app.app_context():
        expense = Expense(
            date=date(2026, 6, 1),
            vendor="Test Vendor",
            category=ExpenseCategory.FILAMENT,
            description="Test expense",
            amount=Decimal("30.00"),
            tax_deductible=True,
        )
        db.session.add(expense)
        db.session.commit()

        assert expense.id is not None
        assert expense.vendor == "Test Vendor"
        assert expense.amount == Decimal("30.00")
        assert expense.tax_deductible is True


def test_market_packing_list_can_be_created(app):
    with app.app_context():
        cat = Category.query.filter_by(slug="mkt-test-cat").first()
        if not cat:
            cat = Category(name="Mkt Test", slug="mkt-test-cat", is_public=True, is_pos_visible=True)
            db.session.add(cat)
            db.session.flush()

        product = Product.query.filter_by(slug="mkt-test-prod").first()
        if not product:
            product = Product(
                name="Mkt Test Product",
                slug="mkt-test-prod",
                category_id=cat.id,
                product_type=ProductType.FINISHED_GOOD,
                status=ProductStatus.ACTIVE,
                base_price=Decimal("15.00"),
                is_public=True,
                is_pos_visible=True,
            )
            db.session.add(product)
            db.session.flush()

        market = Market(
            name="Packing List Market",
            location_name="Market Square",
            event_date=date(2026, 7, 5),
            status=MarketStatus.SCHEDULED,
        )
        db.session.add(market)
        db.session.flush()

        pl = MarketPackingList(
            market_id=market.id,
            product_id=product.id,
            planned_quantity=10,
            packed_quantity=8,
            sold_quantity=5,
            returned_quantity=3,
        )
        db.session.add(pl)
        db.session.commit()

        assert pl.id is not None
        assert pl.planned_quantity == 10
        assert pl.sold_quantity == 5


def test_market_list_page_requires_login(client):
    resp = client.get("/markets/markets/", follow_redirects=True)
    assert resp.status_code == 200
    assert "Sign in" in resp.text or "Login" in resp.text


def test_market_list_page_loads_for_admin(login_admin, client):
    resp = client.get("/markets/markets/", follow_redirects=True)
    assert resp.status_code == 200


def test_market_list_can_sort_by_header(login_admin, client, app):
    with app.app_context():
        db.session.add_all(
            [
                Market(name="Zulu Market", status=MarketStatus.SCHEDULED),
                Market(name="Alpha Market", status=MarketStatus.ACCEPTED),
            ]
        )
        db.session.commit()

    resp = client.get("/markets/markets/?sort=name&dir=asc", follow_redirects=True)

    assert resp.status_code == 200
    assert resp.text.index("Alpha Market") < resp.text.index("Zulu Market")
    assert "sort=name" in resp.text


def test_market_create_page_loads_for_admin(login_admin, client):
    resp = client.get("/markets/markets/new", follow_redirects=True)
    assert resp.status_code == 200


def test_admin_can_create_market(login_admin, client):
    _ensure_csrf_cookie(client)
    resp = client.post("/markets/markets/new", data={
        "name": "Admin Created Market",
        "location_name": "Downtown",
        "city": "Clarksville",
        "state": "TN",
        "event_date": "2026-08-15",
        "status": "scheduled",
        "booth_fee": "75.00",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Admin Created Market" in resp.text


def test_expense_list_page_loads_for_admin(login_admin, client):
    resp = client.get("/expenses/expenses/", follow_redirects=True)
    assert resp.status_code == 200


def test_admin_can_create_expense(login_admin, client):
    _ensure_csrf_cookie(client)
    resp = client.post("/expenses/expenses/new", data={
        "date": "2026-06-15",
        "vendor": "Test Vendor Inc",
        "category": "filament",
        "description": "Test expense via form",
        "amount": "50.00",
        "tax_deductible": "y",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "Test Vendor Inc" in resp.text


def test_market_api_requires_token(client):
    resp = client.get("/api/v1/markets")
    assert resp.status_code == 401


def test_market_api_returns_data_with_token(api_token, client):
    resp = client.get(
        "/api/v1/markets",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "data" in data
    assert "pagination" in data


def test_expense_api_returns_data_with_token(api_token, client):
    resp = client.get(
        "/api/v1/expenses",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "data" in data


def test_markets_csv_export(api_token, client):
    resp = client.get(
        "/api/v1/exports/markets.csv",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "markets.csv" in resp.headers.get("Content-Disposition", "")


def test_expenses_csv_export(api_token, client):
    resp = client.get(
        "/api/v1/exports/expenses.csv",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "expenses.csv" in resp.headers.get("Content-Disposition", "")


def test_market_performance_page_loads(login_admin, client, app):
    with app.app_context():
        market = Market(
            name="Perf Test Market",
            event_date=date(2026, 6, 1),
            status=MarketStatus.COMPLETED,
            actual_revenue=Decimal("500.00"),
            actual_profit=Decimal("300.00"),
        )
        db.session.add(market)
        db.session.commit()
        market_id = market.id

    resp = client.get(f"/markets/{market_id}/performance", follow_redirects=True)
    assert resp.status_code == 200
    assert "Performance" in resp.text


def _ensure_csrf_cookie(client):
    """Fetch a page to get the CSRF token cookie set by Flask-WTF."""
    client.get("/markets/markets/")
