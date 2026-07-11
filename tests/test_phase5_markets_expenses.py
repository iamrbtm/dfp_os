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
    MarketTimelineEvent,
    MarketTimelineEventType,
    MarketWeatherSnapshot,
    PrepTask,
    PrepTaskCategory,
    PrepTaskStatus,
    Product,
    ProductStatus,
    ProductType,
)
from app.services.admin_mutations import create_resource
from app.services.api_tokens import create_api_token
from app.services.markets import fetch_weather_snapshot
from app.services.expenses import create_expense


def _scoped_token(client, *scopes: str) -> str:
    from app.models import User, UserRole

    with client.application.app_context():
        user = User(
            email=f"{'-'.join(scopes)}-api@example.com",
            first_name="Scoped",
            last_name="API",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        _token, raw = create_api_token(user, "Scoped API Token", scopes=list(scopes))
        return raw


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
        task = PrepTask(
            market_id=market.id,
            title="Post preview reel",
            category=PrepTaskCategory.MARKETING,
            status=PrepTaskStatus.OPEN,
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

        assert task.category == PrepTaskCategory.MARKETING
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


def test_market_api_returns_data_with_token(client):
    raw = _scoped_token(client, "markets")
    resp = client.get(
        "/api/v1/markets",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "data" in data
    assert "pagination" in data


def test_expense_api_returns_data_with_token(client):
    raw = _scoped_token(client, "receipts")
    resp = client.get(
        "/api/v1/expenses",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "data" in data


def test_markets_csv_export(client):
    raw = _scoped_token(client, "markets")
    resp = client.get(
        "/api/v1/exports/markets.csv",
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "markets.csv" in resp.headers.get("Content-Disposition", "")


def test_expenses_csv_export(client):
    raw = _scoped_token(client, "receipts")
    resp = client.get(
        "/api/v1/exports/expenses.csv",
        headers={"Authorization": f"Bearer {raw}"},
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
        data={"title": "Pack dragons", "category": "packing", "status": "open"},
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "Pack dragons" in resp.text

    with app.app_context():
        task = PrepTask.query.filter_by(market_id=market_id).one()
        task_id = task.id

    resp = client.post(
        f"/markets/{market_id}/tasks/{task_id}/complete",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(PrepTask, task_id).status == PrepTaskStatus.COMPLETED


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
        "market-weather-snapshots",
        "market-hotel-bookings",
        "market-documents",
    ]:
        resp = client.get(f"/api/v1/{endpoint}")
        assert resp.status_code == 401


# --- Market Application Tracker (Phase 1.1) ---


def test_market_application_tracker_model(app):
    with app.app_context():
        market = Market(
            name="App Tracker Test",
            status=MarketStatus.INTERESTED,
            application_deadline=date(2026, 8, 1),
            application_url="https://example.com/apply",
            application_contact="organizer@example.com",
            booth_rules="No open flames",
            required_documents="Insurance, photos",
            follow_up_date=date(2026, 8, 15),
            worth_repeating=True,
        )
        db.session.add(market)
        db.session.commit()
        assert market.id is not None
        assert market.application_deadline == date(2026, 8, 1)
        assert market.application_url == "https://example.com/apply"
        assert market.application_contact == "organizer@example.com"
        assert market.booth_rules == "No open flames"
        assert market.required_documents == "Insurance, photos"
        assert market.follow_up_date == date(2026, 8, 15)
        assert market.worth_repeating is True


def test_market_application_list_requires_auth(client):
    resp = client.get("/markets/markets/?status=application")
    assert resp.status_code in (302, 401)


def test_market_application_tracker_status_filter(app, client):
    with app.app_context():
        from app.models import User, UserRole
        from flask_login import login_user

        user = User(
            email="app-tracker-admin@example.com",
            first_name="App",
            last_name="Tracker",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("secret")
        db.session.add(user)
        for name, status in [
            ("Spring Festival", MarketStatus.INTERESTED),
            ("Summer Fair", MarketStatus.APPLIED),
            ("Fall Market", MarketStatus.ACCEPTED),
            ("Winter Bazaar", MarketStatus.REJECTED),
            ("Past Event", MarketStatus.COMPLETED),
        ]:
            db.session.add(Market(name=name, status=status))
        db.session.commit()

    with client:
        with app.app_context():
            login_user(user)
        resp = client.get("/markets/markets/?status=application")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Spring Festival" in html
        assert "Summer Fair" in html
        assert "Fall Market" in html
        assert "Winter Bazaar" in html
        assert "Past Event" not in html


def test_market_application_tracker_admin_create(app, client):
    with app.app_context():
        from app.models import User, UserRole
        from flask_login import login_user

        user = User(
            email="app-create-admin@example.com",
            first_name="Create",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

    with client:
        with app.app_context():
            login_user(user)
        _ensure_csrf_cookie(client)
        resp = client.post(
            "/markets/new",
            data={
                "name": "New Application Market",
                "status": MarketStatus.INTERESTED.value,
                "application_deadline": "2026-09-01",
                "application_url": "https://example.org/apply",
                "application_contact": "info@example.org",
                "booth_rules": "Table provided",
                "required_documents": "Business license",
                "follow_up_date": "2026-09-15",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "New Application Market" in html


def test_market_application_api_requires_token(client):
    resp = client.get("/api/v1/markets")
    assert resp.status_code == 401


def _ensure_csrf_cookie(client):
    """Fetch a page to get the CSRF token cookie set by Flask-WTF."""
    client.get("/markets/markets/")


def test_follow_up_queue_requires_auth(client):
    resp = client.get("/prep_tasks/follow_ups/")
    assert resp.status_code == 302


def test_follow_up_queue_loads(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        market = Market.query.filter_by(status=MarketStatus.COMPLETED).first()
        if not market:
            market = Market(name="Follow-Up Test Market", status=MarketStatus.COMPLETED, city="Clarksville", state="TN")
            db.session.add(market)
            db.session.commit()

        from app.models.prep_task import PrepTask, PrepTaskCategory, PrepTaskStatus

        task = PrepTask(
            market_id=market.id,
            title="Thank customer for purchase",
            category=PrepTaskCategory.FOLLOW_UP,
            status=PrepTaskStatus.OPEN,
            follow_up_type="thank_you",
            source="market_follow_up",
        )
        db.session.add(task)
        db.session.commit()

    resp = client.get("/prep_tasks/follow_ups/", headers=admin_headers)
    assert resp.status_code == 200
    assert "Thank customer for purchase" in resp.data.decode("utf-8")


def test_follow_up_complete(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        market = Market(name="Complete FU Market", status=MarketStatus.COMPLETED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.commit()
        task = PrepTask(
            market_id=market.id,
            title="Test follow-up",
            category=PrepTaskCategory.FOLLOW_UP,
            status=PrepTaskStatus.OPEN,
            follow_up_type="thank_you",
            source="market_follow_up",
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    resp = client.post(f"/prep_tasks/follow_ups/{task_id}/complete", headers=admin_headers)
    assert resp.status_code in (200, 302)

    with app.app_context():
        t = db.session.get(PrepTask, task_id)
        assert t is not None
        assert t.status == PrepTaskStatus.COMPLETED


def test_follow_up_reopen(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        market = Market(name="Reopen FU Market", status=MarketStatus.COMPLETED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.commit()
        task = PrepTask(
            market_id=market.id,
            title="Test reopen",
            category=PrepTaskCategory.FOLLOW_UP,
            status=PrepTaskStatus.COMPLETED,
            completed_at=datetime.utcnow(),
            follow_up_type="custom_lead",
            source="market_follow_up",
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    resp = client.post(f"/prep_tasks/follow_ups/{task_id}/reopen", headers=admin_headers)
    assert resp.status_code in (200, 302)

    with app.app_context():
        t = db.session.get(PrepTask, task_id)
        assert t is not None
        assert t.status == PrepTaskStatus.REOPENED
        assert t.completed_at is None


def test_follow_up_archive(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        market = Market(name="Archive FU Market", status=MarketStatus.COMPLETED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.commit()
        task = PrepTask(
            market_id=market.id,
            title="Test archive",
            category=PrepTaskCategory.FOLLOW_UP,
            status=PrepTaskStatus.OPEN,
            follow_up_type="pickup_reminder",
            source="market_follow_up",
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    resp = client.post(f"/prep_tasks/follow_ups/{task_id}/archive", headers=admin_headers)
    assert resp.status_code in (200, 302)

    with app.app_context():
        t = db.session.get(PrepTask, task_id)
        assert t is not None
        assert t.status == PrepTaskStatus.CANCELED


def test_follow_up_generate_for_completed_market(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        from app.services.follow_ups import generate_market_follow_ups

        market = Market(name="Gen FU Market", status=MarketStatus.COMPLETED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.commit()

        tasks = generate_market_follow_ups(market, actor=None)
        assert isinstance(tasks, list)


# --- Table Layout Planner (Phase 1.3) ---


def test_table_layout_model_creation(app):
    with app.app_context():
        from app.models.table_layout import MarketTableLayout, MarketTableSection, MarketTablePlacement, TableSectionType
        market = Market(name="Layout Test Market", status=MarketStatus.SCHEDULED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.flush()

        layout = MarketTableLayout(market_id=market.id, name="Main Table Setup", notes="6ft table")
        db.session.add(layout)
        db.session.flush()

        section = MarketTableSection(
            layout_id=layout.id,
            section_type=TableSectionType.FRONT_CENTER,
            label="Front Center",
            sort_order=1,
        )
        db.session.add(section)
        db.session.flush()

        cat = Category.query.filter_by(slug="layout-test-cat").first()
        if not cat:
            cat = Category(name="Layout Test Cat", slug="layout-test-cat", is_public=True, is_pos_visible=True)
            db.session.add(cat)
            db.session.flush()
        product = Product(
            name="Layout Test Product", slug="layout-test-prod",
            category_id=cat.id, product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE, base_price=Decimal("10.00"),
            is_public=True, is_pos_visible=True,
        )
        db.session.add(product)
        db.session.flush()

        placement = MarketTablePlacement(section_id=section.id, product_id=product.id, quantity=5)
        db.session.add(placement)
        db.session.commit()

        assert layout.id is not None
        assert section.id is not None
        assert placement.id is not None
        assert len(layout.sections) == 1
        assert len(section.placements) == 1
        assert section.placements[0].product.name == "Layout Test Product"


def test_table_layout_list_requires_auth(client):
    resp = client.get("/table_layouts/")
    assert resp.status_code == 302


def test_table_layout_list_loads(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        from app.models.table_layout import MarketTableLayout
        market = Market(name="List Layout Market", status=MarketStatus.SCHEDULED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.flush()
        layout = MarketTableLayout(market_id=market.id, name="List Test Layout")
        db.session.add(layout)
        db.session.commit()

    resp = client.get("/table_layouts/", headers=admin_headers)
    assert resp.status_code == 200
    assert "List Test Layout" in resp.data.decode("utf-8")


def test_table_layout_detail_loads(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        from app.models.table_layout import MarketTableLayout
        market = Market(name="Detail Layout Market", status=MarketStatus.SCHEDULED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.flush()
        layout = MarketTableLayout(market_id=market.id, name="Detail Test Layout")
        db.session.add(layout)
        db.session.commit()
        layout_id = layout.id

    resp = client.get(f"/table_layouts/{layout_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert "Detail Test Layout" in resp.data.decode("utf-8")


def test_table_section_type_enum():
    from app.models.table_layout import TableSectionType
    assert TableSectionType.FRONT_LEFT.value == "front_left"
    assert TableSectionType.FRONT_CENTER.value == "front_center"
    assert TableSectionType.BACK_CENTER.value == "back_center"
    assert TableSectionType.IMPULSE_TRAY.value == "impulse_tray"


def test_table_layout_generates_default_sections(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        market = Market(name="Default Sections Market", status=MarketStatus.SCHEDULED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.flush()
        market_id = market.id

    resp = client.get(f"/table_layouts/new?market_id={market_id}", headers=admin_headers)
    assert resp.status_code == 200

    resp = client.post(f"/table_layouts/new?market_id={market_id}", data={
        "name": "Default Layout Test",
        "csrf_token": _csrf_token_from_response(resp),
    }, follow_redirects=True, headers=admin_headers)
    assert resp.status_code == 200
    assert "Default Layout Test" in resp.data.decode("utf-8") or "Default Layout Test" in resp.text


def _csrf_token_from_response(resp):
    import re
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', resp.text)
    return match.group(1) if match else ""


def test_table_layout_requires_product_for_placement(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        from app.models.table_layout import MarketTableLayout, MarketTableSection, TableSectionType
        market = Market(name="Placement Test Market", status=MarketStatus.SCHEDULED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.flush()
        layout = MarketTableLayout(market_id=market.id, name="Placement Test")
        db.session.add(layout)
        db.session.flush()
        section = MarketTableSection(layout_id=layout.id, section_type=TableSectionType.FRONT_LEFT, label="FL", sort_order=1)
        db.session.add(section)
        db.session.commit()
        section_id = section.id
        layout_id = layout.id

    resp = client.post(f"/table_layouts/{layout_id}/placements/new?section_id={section_id}", data={
        "product_id": "0",
        "quantity": "1",
        "csrf_token": _csrf_token_from_response(client.get(f"/table_layouts/{layout_id}")),
    }, follow_redirects=True, headers=admin_headers)
    assert resp.status_code in (200, 302)


def test_table_layout_archive(app, client, admin_headers):
    _ensure_csrf_cookie(client)
    with app.app_context():
        from app.models.table_layout import MarketTableLayout
        market = Market(name="Archive Layout Market", status=MarketStatus.SCHEDULED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.flush()
        layout = MarketTableLayout(market_id=market.id, name="Archive Test")
        db.session.add(layout)
        db.session.commit()
        layout_id = layout.id

    resp = client.post(f"/table_layouts/{layout_id}/archive", headers=admin_headers)
    assert resp.status_code in (200, 302)

    with app.app_context():
        from app.models.table_layout import MarketTableLayout
        assert db.session.get(MarketTableLayout, layout_id) is None


def test_follow_up_generate_wont_run_for_pending_market(app):
    with app.app_context():
        from app.services.follow_ups import generate_market_follow_ups

        market = Market(name="Pending FU Market", status=MarketStatus.INTERESTED, city="Clarksville", state="TN")
        db.session.add(market)
        db.session.commit()

        tasks = generate_market_follow_ups(market, actor=None)
        assert tasks == []


def test_follow_up_type_enum():
    from app.models.prep_task import FollowUpType

    assert FollowUpType.CUSTOM_LEAD.value == "custom_lead"
    assert FollowUpType.THANK_YOU.value == "thank_you"
    assert FollowUpType.UNPAID_DEPOSIT.value == "unpaid_deposit"
    assert FollowUpType.PICKUP_REMINDER.value == "pickup_reminder"
    assert FollowUpType.QUOTE_FOLLOW_UP.value == "quote_follow_up"
    assert FollowUpType.REQUESTED_COLOR.value == "requested_color"
    assert FollowUpType.REQUESTED_PRODUCT.value == "requested_product"
