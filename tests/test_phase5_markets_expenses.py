from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest

from app.extensions import db
from app.models import (
    Category,
    Expense,
    ExpenseCategory,
    Market,
    MarketDocument,
    MarketDocumentType,
    MarketHotelBooking,
    MarketHotelBookingStatus,
    MarketPackingList,
    MarketStatus,
    MarketTask,
    MarketTaskStatus,
    MarketTaskType,
    MarketTimelineEvent,
    MarketTimelineEventType,
    MarketWeatherSnapshot,
    Product,
    ProductStatus,
    ProductType,
)
from app.services.admin_mutations import create_resource
from app.services.markets import fetch_weather_snapshot
from app.services.expenses import create_expense


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


def test_market_admin_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        market = Market(
            name="Audit Market",
            location_name="Audit Square",
            event_date=date(2026, 9, 1),
            status=MarketStatus.SCHEDULED,
        )
        create_resource(market, actor_id=123)

    assert any(call["action"] == "market.created" for call in calls)


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


def test_market_command_center_models_can_be_created(app):
    with app.app_context():
        market = Market(name="Ops Market", event_date=date(2026, 8, 1), status=MarketStatus.SCHEDULED)
        db.session.add(market)
        db.session.flush()
        task = MarketTask(
            market_id=market.id,
            title="Post preview reel",
            task_type=MarketTaskType.MARKETING,
            status=MarketTaskStatus.OPEN,
        )
        timeline = MarketTimelineEvent(
            market_id=market.id,
            title="Load in",
            event_type=MarketTimelineEventType.LOAD_IN,
        )
        weather = MarketWeatherSnapshot(
            market_id=market.id,
            provider="weather.gov",
            fetched_at=datetime(2026, 6, 17, 12, 0),
            short_forecast="Sunny",
        )
        hotel = MarketHotelBooking(
            market_id=market.id,
            hotel_name="Clarksville Inn",
            status=MarketHotelBookingStatus.BOOKED,
            cost=Decimal("120.00"),
        )
        document = MarketDocument(
            market_id=market.id,
            original_filename="permit.pdf",
            stored_filename="permit.pdf",
            document_type=MarketDocumentType.PERMIT,
        )
        db.session.add_all([task, timeline, weather, hotel, document])
        db.session.commit()

        assert market.tasks[0].task_type == MarketTaskType.MARKETING
        assert market.timeline_events[0].event_type == MarketTimelineEventType.LOAD_IN
        assert market.weather_snapshots[0].short_forecast == "Sunny"
        assert market.hotel_bookings[0].hotel_name == "Clarksville Inn"
        assert market.documents[0].document_type == MarketDocumentType.PERMIT


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


def test_expense_service_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        expense = Expense(
            date=date(2026, 6, 20),
            vendor="Audit Vendor",
            category=ExpenseCategory.OTHER,
            description="Audit me",
            amount=Decimal("42.00"),
            tax_deductible=False,
        )
        create_expense(expense, actor_id=123)

    assert any(call["action"] == "expense.created" for call in calls)


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


def test_market_detail_renders_command_center_sections(login_admin, client, app):
    with app.app_context():
        market = Market(
            name="Command Center Market",
            event_date=date(2026, 9, 1),
            status=MarketStatus.SCHEDULED,
        )
        db.session.add(market)
        db.session.commit()
        market_id = market.id

    resp = client.get(f"/markets/{market_id}", follow_redirects=True)
    assert resp.status_code == 200
    for heading in [
        "Event &amp; Logistics",
        "Financial Overview",
        "Products &amp; Inventory",
        "Schedule &amp; Timeline",
        "Tasks &amp; Marketing",
        "Weather &amp; Conditions",
        "Travel &amp; Accommodations",
        "Documents &amp; Files",
    ]:
        assert heading in resp.text


def test_market_task_create_and_complete_htmx(login_admin, client, app):
    with app.app_context():
        market = Market(name="Task Market", status=MarketStatus.SCHEDULED)
        db.session.add(market)
        db.session.commit()
        market_id = market.id

    resp = client.post(
        f"/markets/{market_id}/tasks",
        data={"title": "Pack dragons", "task_type": "packing", "status": "open"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "Pack dragons" in resp.text

    with app.app_context():
        task = MarketTask.query.filter_by(market_id=market_id).one()
        task_id = task.id

    resp = client.post(
        f"/markets/{market_id}/tasks/{task_id}/complete",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(MarketTask, task_id).status == MarketTaskStatus.COMPLETED


def test_market_timeline_hotel_and_packing_quick_add_htmx(login_admin, client, app, catalog_product):
    with app.app_context():
        market = Market(name="HTMX Market", status=MarketStatus.SCHEDULED)
        db.session.add(market)
        db.session.commit()
        market_id = market.id

    timeline_resp = client.post(
        f"/markets/{market_id}/timeline",
        data={"title": "Vendor load-in", "event_type": "load_in"},
        headers={"HX-Request": "true"},
    )
    assert timeline_resp.status_code == 200
    assert "Vendor load-in" in timeline_resp.text

    hotel_resp = client.post(
        f"/markets/{market_id}/hotels",
        data={"hotel_name": "Market Hotel", "status": "booked", "cost": "90.00"},
        headers={"HX-Request": "true"},
    )
    assert hotel_resp.status_code == 200
    assert "Market Hotel" in hotel_resp.text

    packing_resp = client.post(
        f"/markets/{market_id}/packing-list/quick-add",
        data={
            "product_id": catalog_product,
            "variant_id": 0,
            "planned_quantity": 12,
            "packed_quantity": 5,
            "sold_quantity": 0,
            "returned_quantity": 0,
        },
        headers={"HX-Request": "true"},
    )
    assert packing_resp.status_code == 200
    assert "Rainbow Dragon" in packing_resp.text


def test_market_document_upload_validation(login_admin, client, app):
    with app.app_context():
        market = Market(name="Docs Market", status=MarketStatus.SCHEDULED)
        db.session.add(market)
        db.session.commit()
        market_id = market.id

    resp = client.post(
        f"/markets/{market_id}/documents",
        data={
            "document_type": "permit",
            "file": (BytesIO(b"not allowed"), "script.exe"),
        },
        content_type="multipart/form-data",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "not supported" in resp.text


def test_weather_fetch_requires_coordinates(app):
    with app.app_context():
        market = Market(name="No Coordinates", status=MarketStatus.SCHEDULED)
        db.session.add(market)
        db.session.commit()
        with pytest.raises(ValueError):
            fetch_weather_snapshot(market)


def test_weather_fetch_stores_matching_forecast(app, monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            if "points" in url:
                return FakeResponse({"properties": {"forecast": "https://api.weather.gov/gridpoints/test"}})
            return FakeResponse(
                {
                    "properties": {
                        "periods": [
                            {
                                "startTime": "2026-09-01T09:00:00-05:00",
                                "temperature": 72,
                                "shortForecast": "Sunny",
                                "detailedForecast": "Sunny and calm.",
                                "probabilityOfPrecipitation": {"value": 5},
                                "windSpeed": "5 mph",
                                "windDirection": "N",
                            }
                        ]
                    }
                }
            )

    monkeypatch.setattr("app.services.markets.httpx.Client", FakeClient)
    with app.app_context():
        market = Market(
            name="Weather Market",
            event_date=date(2026, 9, 1),
            latitude=36.5298,
            longitude=-87.3595,
            status=MarketStatus.SCHEDULED,
        )
        db.session.add(market)
        db.session.commit()
        snapshot = fetch_weather_snapshot(market)
        assert snapshot.short_forecast == "Sunny"
        assert snapshot.precipitation_probability == 5


def test_new_market_api_resources_require_token(client):
    for endpoint in [
        "market-timeline-events",
        "market-tasks",
        "market-weather-snapshots",
        "market-hotel-bookings",
        "market-documents",
    ]:
        resp = client.get(f"/api/v1/{endpoint}")
        assert resp.status_code == 401


def test_market_tasks_api_returns_data_with_token(api_token, client):
    resp = client.get(
        "/api/v1/market-tasks",
        headers={"Authorization": f"Bearer {api_token}"},
    )
    assert resp.status_code == 200
    assert "data" in resp.get_json()


def _ensure_csrf_cookie(client):
    """Fetch a page to get the CSRF token cookie set by Flask-WTF."""
    client.get("/markets/markets/")
