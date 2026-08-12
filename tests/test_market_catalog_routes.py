from __future__ import annotations

from datetime import date

from app.extensions import db
from app.services.api_tokens import create_api_token
from app.services.market_catalog import create_category, create_listing
from app.services.market_catalog_recurrence import build_rrule


def _seed_listing(app) -> int:
    with app.app_context():
        category = create_category(name="Holiday", description="Holiday markets")
        listing = create_listing(
            actor=None,
            tiers=[{"label": "10x10", "price": 75.00}],
            name="Route Test Market",
            category_id=category.id,
            city="Clarksville",
            state="TN",
            is_recurring=True,
            rrule=build_rrule("yearly", month=10, weekday="SA", week_number=3),
            interest_level="interested",
        )
        return listing.id


def test_catalog_list_requires_login(client):
    r = client.get("/market-catalog/", follow_redirects=False)
    assert r.status_code == 302
    assert "/auth/login" in r.location


def test_catalog_list_loads_for_admin(client, login_admin):
    r = client.get("/market-catalog/")
    assert r.status_code == 200
    assert b"Market Catalog" in r.data
    assert b"Import" in r.data
    assert b">AI<" in r.data


def test_categories_page_loads(client, login_admin):
    r = client.get("/market-catalog/categories")
    assert r.status_code == 200


def test_create_listing_form_loads(client, login_admin):
    r = client.get("/market-catalog/listings/new")
    assert r.status_code == 200


def test_ai_import_creates_market_catalog_listing(client, login_admin, app, monkeypatch):
    payload = {
        "name": "Imported AI Market",
        "description": "Market extracted from a flyer.",
        "website_url": "https://example.com/market",
        "category_hint": "craft_market",
        "interest_level": "watching",
        "location": {
            "location_name": "Downtown Square",
            "address": "1 Main St",
            "city": "Clarksville",
            "state": "TN",
            "zip_code": "37040",
            "country": "US",
        },
        "timing": {
            "default_start_time": "09:00",
            "default_end_time": "15:00",
            "timezone": "America/Chicago",
            "is_recurring": False,
            "rrule": None,
            "recurrence_description": None,
            "anchor_date": "2026-09-12",
            "next_occurrence_date": "2026-09-12",
        },
        "scale": {"estimated_vendor_count": 35, "estimated_attendee_count": None},
        "amenities": {
            "power_available": False,
            "wifi_available": False,
            "food_available": True,
            "restrooms_available": True,
            "indoor": False,
            "covered_outdoor": False,
            "outdoor": True,
            "parking_notes": "Street parking nearby.",
        },
        "organizer": {
            "name": "Market Organizer",
            "email": "organizer@example.com",
            "phone": "555-0100",
            "application_url": "https://example.com/apply",
        },
        "rules": {"booth_rules": "No generators.", "required_documents": "Sales tax permit."},
        "booth_tiers": [
            {"label": "Standard", "dimensions": "10x10", "price": 50.0, "sort_order": 0}
        ],
        "field_confidence": {
            "identity": "high",
            "location": "high",
            "timing": "high",
            "scale": "medium",
            "amenities": "medium",
            "organizer": "high",
            "rules": "medium",
            "booth_tiers": "high",
        },
        "sources_consulted": [
            {"url": "https://example.com/market", "purpose": "Original input URL"}
        ],
        "search_queries_used": [],
        "research_complete": True,
        "extraction_notes": "Fetched the provided source. Human should verify rules.",
    }

    def fake_generate_market_catalog_extraction(*, user_input, uploaded_file=None):
        assert user_input == "https://example.com/market"
        assert uploaded_file is None
        return payload

    monkeypatch.setattr(
        "app.blueprints.market_catalog.routes.generate_market_catalog_extraction",
        fake_generate_market_catalog_extraction,
    )

    r = client.post(
        "/market-catalog/listings/import/ai",
        data={"ai_input": "https://example.com/market", "csrf_token": _csrf(client)},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.location.endswith("/market-catalog/listings")

    with app.app_context():
        from app.models import MarketCatalogListing

        listing = MarketCatalogListing.query.filter_by(name="Imported AI Market").first()
        assert listing is not None
        assert listing.city == "Clarksville"
        assert listing.anchor_date == date(2026, 9, 12)
        assert listing.next_occurrence_date == date(2026, 9, 12)
        assert listing.booth_tiers[0].label == "Standard"
        assert str(listing.booth_tiers[0].price) == "50.00"
        assert "AI extraction notes" in listing.notes


def test_detail_page_loads(client, login_admin, app):
    listing_id = _seed_listing(app)
    r = client.get(f"/market-catalog/listings/{listing_id}")
    assert r.status_code == 200
    assert b"Route Test Market" in r.data


def test_booking_form_loads(client, login_admin, app):
    listing_id = _seed_listing(app)
    r = client.get(f"/market-catalog/listings/{listing_id}/book")
    assert r.status_code == 200
    assert b"Book this market" in r.data


def test_book_listing_creates_market(client, login_admin, app):
    listing_id = _seed_listing(app)
    r = client.post(
        f"/market-catalog/listings/{listing_id}/book",
        data={
            "event_date": "2026-10-17",
            "booth_tier_id": "",
            "status": "interested",
            "apply_corner_premium": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "/markets/" in r.location


def test_occurrences_endpoint_returns_json(client, login_admin, app):
    listing_id = _seed_listing(app)
    r = client.get(f"/market-catalog/listings/{listing_id}/occurrences")
    assert r.status_code == 200
    data = r.get_json()
    assert "occurrences" in data
    assert len(data["occurrences"]) > 0


def test_recurrence_preview_fixed_date(client, login_admin):
    r = client.post(
        "/market-catalog/recurrence-preview",
        data={
            "recurrence_pattern": "fixed_day_of_month",
            "recurrence_month": "7",
            "recurrence_day": "4",
            "recurrence_override": "0",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["rrule"] == "FREQ=YEARLY;BYMONTH=7;BYMONTHDAY=4"
    assert data["human"] == "July 4th, annually."
    assert len(data["next_two"]) >= 2


def test_recurrence_preview_weekly_month_window(client, login_admin):
    r = client.post(
        "/market-catalog/recurrence-preview",
        data={
            "recurrence_pattern": "weekly",
            "recurrence_weekday": "SA",
            "recurrence_start_month": "3",
            "recurrence_end_month": "10",
            "recurrence_override": "0",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["rrule"] == "FREQ=WEEKLY;BYDAY=SA;BYMONTH=3,4,5,6,7,8,9,10"


def test_recurrence_preview_one_off(client, login_admin):
    r = client.post(
        "/market-catalog/recurrence-preview",
        data={
            "recurrence_pattern": "one_off",
            "recurrence_anchor": "2026-07-04",
            "recurrence_override": "0",
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["rrule"] is None
    assert data["dtstart"] == "2026-07-04"


def test_recurrence_preview_validation_error(client, login_admin):
    r = client.post(
        "/market-catalog/recurrence-preview",
        data={
            "recurrence_pattern": "weekly",
            "recurrence_override": "0",
        },
    )
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_create_listing_via_wizard(client, login_admin):
    r = client.post(
        "/market-catalog/listings/new",
        data={
            "name": "Wizard Market",
            "interest_level": "interested",
            "is_recurring": "y",
            "recurrence_pattern": "nth_weekday_of_month",
            "recurrence_month": "10",
            "recurrence_nth": "3",
            "recurrence_weekday": "SA",
            "recurrence_override": "0",
            "tier_label": ["10x10"],
            "tier_sort": ["0"],
            "csrf_token": _csrf(client),
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    with client.application.app_context():
        from app.models import MarketCatalogListing

        listing = MarketCatalogListing.query.filter_by(name="Wizard Market").first()
        assert listing is not None
        assert listing.rrule == "FREQ=YEARLY;BYMONTH=10;BYDAY=SA;BYSETPOS=3"
        assert listing.is_recurring is True


def test_create_listing_with_blank_tier_corner_premium(client, login_admin):
    # An empty ``corner_premium`` (and price) must be stored as NULL, not as
    # an empty string that breaks the Numeric column.
    r = client.post(
        "/market-catalog/listings/new",
        data={
            "name": "Blank Corner Premium",
            "interest_level": "interested",
            "recurrence_pattern": "one_off",
            "recurrence_anchor": "2026-11-15",
            "recurrence_override": "0",
            "rrule": "",
            "tier_label": ["Booth Only"],
            "tier_dimensions": [""],
            "tier_price": [""],
            "tier_corner": [""],
            "tier_notes": [""],
            "tier_sort": ["0"],
            "csrf_token": _csrf(client),
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    with client.application.app_context():
        from app.models import MarketCatalogListing

        listing = MarketCatalogListing.query.filter_by(name="Blank Corner Premium").first()
        assert listing is not None
        tier = listing.booth_tiers[0]
        assert tier.price is None
        assert tier.corner_premium is None
        assert tier.dimensions is None
        assert tier.notes is None


def test_create_one_off_via_wizard_sets_anchor_and_next(client, login_admin):
    r = client.post(
        "/market-catalog/listings/new",
        data={
            "name": "Wizard OneOff",
            "interest_level": "interested",
            "recurrence_pattern": "one_off",
            "recurrence_anchor": "2026-12-25",
            "recurrence_override": "0",
            "rrule": "",
            "tier_label": ["10x10"],
            "tier_sort": ["0"],
            "csrf_token": _csrf(client),
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    with client.application.app_context():
        from app.models import MarketCatalogListing

        listing = MarketCatalogListing.query.filter_by(name="Wizard OneOff").first()
        assert listing is not None
        assert listing.anchor_date == date(2026, 12, 25)
        assert listing.rrule is None
        assert listing.is_recurring is False
        assert listing.next_occurrence_date == date(2026, 12, 25)


def test_create_one_off_without_anchor_shows_field_error(client, login_admin):
    r = client.post(
        "/market-catalog/listings/new",
        data={
            "name": "Wizard OneOff Missing",
            "interest_level": "interested",
            "recurrence_pattern": "one_off",
            "recurrence_override": "0",
            "rrule": "",
            "tier_label": ["10x10"],
            "tier_sort": ["0"],
            "csrf_token": _csrf(client),
        },
        follow_redirects=False,
    )
    # Form-level validation rejects the submission and re-renders the form.
    assert r.status_code == 200
    assert b"Pick a one-time date for this market." in r.data
    with client.application.app_context():
        from app.models import MarketCatalogListing

        assert MarketCatalogListing.query.filter_by(name="Wizard OneOff Missing").first() is None


def test_recurrence_preview_returns_nth_for_editing_recurring(client, login_admin, app):
    """The preview endpoint must receive the wizard payload from the edit form.

    Regression: the edit form used to render ``recurrence_pattern`` and
    ``recurrence_override`` twice (once via ``form.hidden_tag()`` and once in
    the hidden div), which made the browser submit the values as empty
    strings and the preview endpoint treated the listing as a one-off.
    """
    with app.app_context():
        cat = create_category(name="Recurring Edit Preview")
        listing = create_listing(
            actor=None,
            tiers=[{"label": "10x10", "price": 75.00}],
            name="Edit Preview Recurring",
            category_id=cat.id,
            is_recurring=True,
            rrule="FREQ=YEARLY;BYMONTH=9;BYDAY=SA;BYSETPOS=3",
            anchor_date=__import__("datetime").date(2026, 9, 19),
            interest_level="interested",
        )
        listing_id = listing.id

    page = client.get(f"/market-catalog/listings/{listing_id}/edit")
    assert page.status_code == 200
    # Each wizard field name must appear exactly once in the rendered HTML so
    # the browser submits a single value.
    html = page.data.decode()
    assert html.count('name="recurrence_pattern"') == 1
    assert html.count('name="recurrence_override"') == 1
    assert html.count('name="recurrence_weekday"') == 1
    assert html.count('name="recurrence_month"') == 1
    assert html.count('name="recurrence_nth"') == 1

    # The preview endpoint, given the wizard payload for an nth weekday,
    # must return the correct recurrence description and rrule.
    csrf = _csrf(client)
    resp = client.post(
        "/market-catalog/recurrence-preview",
        data={
            "csrf_token": csrf,
            "recurrence_pattern": "nth_weekday_of_month",
            "recurrence_month": "9",
            "recurrence_nth": "3",
            "recurrence_weekday": "SA",
            "recurrence_override": "0",
            "recurrence_anchor": "2026-09-19",
            "rrule": "FREQ=YEARLY;BYMONTH=9;BYDAY=SA;BYSETPOS=3",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["rrule"] == "FREQ=YEARLY;BYMONTH=9;BYDAY=SA;BYSETPOS=3"
    assert body["human"] == "3rd Saturday of September, annually."


def test_edit_form_prefills_anchor_for_one_off(client, login_admin, app):
    with app.app_context():
        cat = create_category(name="Holiday Test")
        listing = create_listing(
            actor=None,
            tiers=[{"label": "10x10", "price": 75.00}],
            name="Edit Prefill OneOff",
            category_id=cat.id,
            anchor_date=date(2026, 11, 1),
            interest_level="interested",
        )
        listing_id = listing.id

    r = client.get(f"/market-catalog/listings/{listing_id}/edit")
    assert r.status_code == 200
    assert b'value="2026-11-01"' in r.data
    assert b'name="recurrence_anchor"' in r.data


def test_edit_form_prefills_wizard_for_recurring(client, login_admin, app):
    with app.app_context():
        cat = create_category(name="Recurring Test")
        listing = create_listing(
            actor=None,
            tiers=[{"label": "10x10", "price": 75.00}],
            name="Edit Prefill Recurring",
            category_id=cat.id,
            is_recurring=True,
            rrule="FREQ=YEARLY;BYMONTH=10;BYDAY=SA;BYSETPOS=3",
            interest_level="interested",
        )
        listing_id = listing.id

    r = client.get(f"/market-catalog/listings/{listing_id}/edit")
    assert r.status_code == 200
    # Server-side wizard prefill sets the hidden pattern + sub-fields.
    assert b'name="recurrence_pattern" type="hidden" value="nth_weekday_of_month"' in r.data
    assert b'name="recurrence_weekday"' in r.data


def test_detail_page_shows_one_off_anchor(client, login_admin, app):
    with app.app_context():
        cat = create_category(name="OneOff Detail")
        listing = create_listing(
            actor=None,
            tiers=[{"label": "10x10", "price": 75.00}],
            name="Detail OneOff",
            category_id=cat.id,
            anchor_date=date(2026, 11, 1),
            interest_level="interested",
        )
        listing_id = listing.id

    r = client.get(f"/market-catalog/listings/{listing_id}")
    assert r.status_code == 200
    assert b"Nov 01, 2026" in r.data
    assert b"Market Date" in r.data


def test_api_creates_listing_with_anchor_date(client, login_admin, app):
    with app.app_context():
        user = db.session.get(__import__("app.models", fromlist=["User"]).User, login_admin["id"])
        _, raw_token = create_api_token(user=user, name="anchor-test", scopes=["markets"])
    r = client.post(
        "/api/v1/market-catalog-listings",
        headers={"Authorization": f"Bearer {raw_token}"},
        json={
            "name": "API Anchor Test",
            "interest_level": "interested",
            "anchor_date": "2026-09-15",
            "is_recurring": False,
        },
    )
    assert r.status_code == 201, r.data
    with app.app_context():
        from app.models import MarketCatalogListing

        listing = MarketCatalogListing.query.filter_by(name="API Anchor Test").first()
        assert listing is not None
        assert listing.anchor_date == date(2026, 9, 15)
        assert listing.next_occurrence_date == date(2026, 9, 15)


def _csrf(client):
    r = client.get("/market-catalog/listings/new")
    html = r.data.decode()
    import re

    m = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', html)
    return m.group(1) if m else ""


def test_api_market_categories_requires_token(client):
    r = client.get("/api/v1/market-categories")
    assert r.status_code == 401


def test_api_market_categories_with_token(client, login_admin, app):
    with app.app_context():
        from app.models import User

        user = db.session.get(User, login_admin["id"])
        _, raw_token = create_api_token(user=user, name="test-token", scopes=["markets"])
    r = client.get(
        "/api/v1/market-categories",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert r.status_code == 200


def test_api_market_catalog_listings_with_token(client, login_admin, app):
    _seed_listing(app)
    with app.app_context():
        from app.models import User

        user = db.session.get(User, login_admin["id"])
        _, raw_token = create_api_token(user=user, name="test-token", scopes=["markets"])
    r = client.get(
        "/api/v1/market-catalog-listings",
        headers={"Authorization": f"Bearer {raw_token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "data" in data or isinstance(data, list)


def test_feature_flag_disabled_blocks_route(client, login_admin, app):
    with app.app_context():
        from app.models import FeatureFlag

        flag = FeatureFlag.query.filter_by(key="module.markets.enabled").first()
        if flag is None:
            flag = FeatureFlag(key="module.markets.enabled", enabled=False)
            db.session.add(flag)
        else:
            flag.enabled = False
        db.session.commit()
    r = client.get("/market-catalog/")
    assert r.status_code == 403
    with app.app_context():
        from app.models import FeatureFlag

        flag = FeatureFlag.query.filter_by(key="module.markets.enabled").first()
        flag.enabled = True
        db.session.commit()
