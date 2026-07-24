from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Market, MarketStatus, UserRole
from app.services.api_tokens import create_api_token
from app.services.report_studio import (
    get_data_quality_summary,
    get_market_application_pipeline_report,
    get_report_catalog,
    get_vendor_market_heat_map,
)


def _admin_token(client):
    from app.models import User

    with client.application.app_context():
        user = User(
            email="rs-admin@example.com",
            first_name="Report",
            last_name="Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        token, raw = create_api_token(user, "RS API Token", scopes=["report_studio"])
        return raw


def _create_market(
    name: str = "Test Market",
    status: MarketStatus = MarketStatus.COMPLETED,
    city: str | None = "Clarksville",
    state: str | None = "TN",
    booth_fee: Decimal | None = Decimal("50.00"),
    application_fee: Decimal | None = Decimal("25.00"),
    latitude: float | None = 36.5,
    longitude: float | None = -87.4,
    event_date: date | None = None,
    worth_repeating: bool | None = None,
    follow_up_date: date | None = None,
    application_deadline: date | None = None,
    required_documents: str | None = "Permit, Insurance",
):
    market = Market(
        name=name,
        status=status,
        city=city,
        state=state,
        booth_fee=booth_fee,
        application_fee=application_fee,
        latitude=latitude,
        longitude=longitude,
        event_date=event_date or date(2026, 6, 1),
        worth_repeating=worth_repeating,
        follow_up_date=follow_up_date,
        application_deadline=application_deadline,
        required_documents=required_documents,
    )
    db.session.add(market)
    db.session.flush()
    return market


def test_get_report_catalog_returns_reports(app):
    with app.app_context():
        catalog = get_report_catalog()
        assert len(catalog) > 0
        categories = {r["category"] for r in catalog}
        assert "Markets" in categories
        market_reports = [r for r in catalog if r["category"] == "Markets"]
        assert any("heat" in r["key"] for r in market_reports)
        assert any("tracker" in r["key"] for r in market_reports)


def test_report_catalog_has_urls_for_built_reports(app):
    with app.app_context():
        catalog = get_report_catalog()
        for report in catalog:
            if report["key"] in ("vendor-market-heat-map", "market-application-tracker"):
                assert report["url"] is not None


def test_data_quality_summary_no_markets(app):
    with app.app_context():
        summary = get_data_quality_summary()
        assert summary["total_markets"] == 0
        assert len(summary["warnings"]) > 0
        assert any("No markets created" in w["message"] for w in summary["warnings"])


def test_data_quality_summary_with_completed_markets(app):
    with app.app_context():
        _create_market("Completed Market", MarketStatus.COMPLETED)
        summary = get_data_quality_summary()
        assert summary["total_markets"] >= 1
        assert summary["completed_markets"] >= 1


def test_data_quality_summary_missing_coords(app):
    with app.app_context():
        _create_market("No Coords Market", MarketStatus.SCHEDULED, latitude=None, longitude=None)
        summary = get_data_quality_summary()
        assert any("coordinates" in w["message"] for w in summary["warnings"])


def test_vendor_market_heat_map_empty(app):
    with app.app_context():
        data = get_vendor_market_heat_map({})
        assert isinstance(data, list)


def test_vendor_market_heat_map_with_data(app):
    with app.app_context():
        _create_market("Heat Map Market", MarketStatus.COMPLETED, booth_fee=Decimal("75"), application_fee=Decimal("25"))
        data = get_vendor_market_heat_map({})
        assert len(data) >= 1
        assert any(m["name"] == "Heat Map Market" for m in data)
        entry = next(m for m in data if m["name"] == "Heat Map Market")
        assert entry["has_coordinates"] is True
        assert entry["booth_fee"] == 75.0


def test_vendor_market_heat_map_min_profit_filter(app):
    with app.app_context():
        _create_market("High Profit", MarketStatus.COMPLETED, booth_fee=Decimal("10"))
        data = get_vendor_market_heat_map({"min_profit": "1000"})
        for m in data:
            assert m["profit"] >= 1000


def test_vendor_market_heat_map_status_filter(app):
    with app.app_context():
        _create_market("Scheduled Market", MarketStatus.SCHEDULED, name="SchedMarket")
        data = get_vendor_market_heat_map({"status": "scheduled"})
        assert all(m["status"] == "scheduled" for m in data)


def test_market_application_pipeline_report_empty(app):
    with app.app_context():
        report = get_market_application_pipeline_report({})
        assert report["total_applications"] == 0
        assert report["pipeline"] == []


def test_market_application_pipeline_report_with_data(app):
    with app.app_context():
        _create_market(
            "Pipeline Market",
            MarketStatus.APPLIED,
            application_deadline=date(2026, 7, 15),
            booth_fee=Decimal("100"),
            application_fee=Decimal("50"),
            follow_up_date=date(2026, 6, 1),
        )
        report = get_market_application_pipeline_report({})
        assert report["total_applications"] >= 1
        assert report["status_counts"].get("applied", 0) >= 1
        assert report["fees_at_risk"] >= 150.0


def test_market_application_pipeline_report_metrics(app):
    with app.app_context():
        _create_market("Interested Market", MarketStatus.INTERESTED, application_deadline=date(2026, 8, 1))
        report = get_market_application_pipeline_report({})
        assert report["upcoming_deadlines"] >= 1
        assert report["total_applications"] >= 1


def test_market_application_pipeline_missing_docs(app):
    with app.app_context():
        _create_market("No Docs Market", MarketStatus.APPLIED, required_documents=None)
        report = get_market_application_pipeline_report({})
        assert report["missing_documents_count"] >= 1


def test_route_home_requires_auth(client):
    resp = client.get("/report-studio/")
    assert resp.status_code == 302


def test_route_home_loads_for_admin(client, app):
    with app.app_context():
        _create_market("RS Test Market", MarketStatus.COMPLETED)
    client.post("/auth/login", data={"email": "owner@example.com", "password": "super-secret"})
    resp = client.get("/report-studio/")
    assert resp.status_code == 200
    assert b"Report Studio" in resp.data


def test_route_home_empty_state(client, app):
    client.post("/auth/login", data={"email": "owner@example.com", "password": "super-secret"})
    resp = client.get("/report-studio/")
    assert resp.status_code == 200


def test_route_heat_map_loads(client, app):
    with app.app_context():
        _create_market("HM Market", MarketStatus.COMPLETED)
    client.post("/auth/login", data={"email": "owner@example.com", "password": "super-secret"})
    resp = client.get("/report-studio/heat-map")
    assert resp.status_code == 200
    assert b"Vendor Market Heat Map" in resp.data


def test_route_heat_map_empty(client, app):
    client.post("/auth/login", data={"email": "owner@example.com", "password": "super-secret"})
    resp = client.get("/report-studio/heat-map")
    assert resp.status_code == 200


def test_route_application_tracker_loads(client, app):
    with app.app_context():
        _create_market("AT Market", MarketStatus.APPLIED)
    client.post("/auth/login", data={"email": "owner@example.com", "password": "super-secret"})
    resp = client.get("/report-studio/application-tracker")
    assert resp.status_code == 200
    assert b"Market Application Tracker" in resp.data


def test_route_application_tracker_empty(client, app):
    client.post("/auth/login", data={"email": "owner@example.com", "password": "super-secret"})
    resp = client.get("/report-studio/application-tracker")
    assert resp.status_code == 200


def test_api_reports_requires_token(client):
    resp = client.get("/api/v1/report-studio/reports")
    assert resp.status_code == 401


def test_api_reports_returns_data(client, app):
    token = _admin_token(client)
    resp = client.get(
        "/api/v1/report-studio/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "data" in data
    assert "catalog" in data["data"]
    assert "data_quality" in data["data"]


def test_api_heat_map_requires_token(client):
    resp = client.get("/api/v1/report-studio/heat-map")
    assert resp.status_code == 401


def test_api_heat_map_returns_data(client, app):
    token = _admin_token(client)
    resp = client.get(
        "/api/v1/report-studio/heat-map",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "data" in data


def test_api_application_tracker_requires_token(client):
    resp = client.get("/api/v1/report-studio/application-tracker")
    assert resp.status_code == 401


def test_api_application_tracker_returns_data(client, app):
    token = _admin_token(client)
    resp = client.get(
        "/api/v1/report-studio/application-tracker",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "data" in data


def test_api_heat_map_csv_export(client, app):
    token = _admin_token(client)
    resp = client.get(
        "/api/v1/report-studio/heat-map/csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.content_type == "text/csv"
    assert "text/csv" in resp.content_type


def test_api_application_tracker_csv_export(client, app):
    token = _admin_token(client)
    resp = client.get(
        "/api/v1/report-studio/application-tracker/csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.content_type == "text/csv"


def test_module_blocked_when_disabled(client, app):
    from app.models import FeatureFlag

    with app.app_context():
        flag = FeatureFlag.query.filter_by(key="module.report_studio.enabled").first()
        if flag is None:
            flag = FeatureFlag(key="module.report_studio.enabled", enabled=False)
            db.session.add(flag)
        else:
            flag.enabled = False
        db.session.commit()
    client.post("/auth/login", data={"email": "owner@example.com", "password": "super-secret"})
    resp = client.get("/report-studio/")
    assert resp.status_code == 403


def test_staff_can_access_report_studio(client, app):
    from app.models import User

    with app.app_context():
        user = User(
            email="staff-rs@example.com",
            first_name="Staff",
            last_name="RS",
            role=UserRole.STAFF,
            is_active=True,
        )
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
    client.post("/auth/login", data={"email": "staff-rs@example.com", "password": "secret"})
    resp = client.get("/report-studio/")
    assert resp.status_code == 200
