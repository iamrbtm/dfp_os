from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import MarketCatalogListing, MarketStatus
from app.services.market_catalog import (
    archive_listing,
    create_category,
    create_listing,
    get_listing,
    update_listing,
)
from app.services.market_catalog_booking import book_from_catalog, suggest_booking_dates
from app.services.market_catalog_recurrence import build_rrule
from app.services.market_catalog_sync import sync_listing_occurrences


def _make_listing(app) -> MarketCatalogListing:
    with app.app_context():
        category = create_category(name="Holiday", description="Holiday markets")
        listing = create_listing(
            actor=None,
            tiers=[
                {
                    "label": "10x10",
                    "dimensions": "10ft x 10ft",
                    "price": Decimal("75.00"),
                    "corner_premium": Decimal("25.00"),
                },
                {"label": "10x20", "price": Decimal("130.00")},
            ],
            name="Test Holiday Market",
            category_id=category.id,
            city="Clarksville",
            state="TN",
            power_available=True,
            wifi_available=True,
            food_available=True,
            is_recurring=True,
            rrule=build_rrule("yearly", month=10, weekday="SA", week_number=3),
            interest_level="priority",
        )
        return listing


def test_create_listing_with_booth_tiers(app):
    listing = _make_listing(app)
    with app.app_context():
        fetched = get_listing(listing.id)
        assert fetched is not None
        assert fetched.name == "Test Holiday Market"
        assert len(fetched.booth_tiers) == 2
        assert fetched.booth_tiers[0].label == "10x10"
        assert fetched.booth_tiers[0].price == Decimal("75.00")
        assert fetched.booth_tiers[1].price == Decimal("130.00")


def test_update_listing_replaces_booth_tiers(app):
    listing = _make_listing(app)
    with app.app_context():
        fetched = get_listing(listing.id)
        update_listing(
            fetched,
            actor=None,
            tiers=[{"label": "Single", "price": Decimal("100.00")}],
            name="Updated Market Name",
            category_id=fetched.category_id,
            description="updated",
            website_url=None,
            location_name=None,
            address=None,
            city=None,
            state=None,
            zip_code=None,
            latitude=None,
            longitude=None,
            default_start_time=None,
            default_end_time=None,
            timezone=None,
            is_recurring=True,
            rrule=fetched.rrule,
            recurrence_description=None,
            estimated_vendor_count=None,
            estimated_attendee_count=None,
            power_available=False,
            wifi_available=False,
            food_available=False,
            restrooms_available=False,
            indoor=False,
            covered_outdoor=False,
            outdoor=False,
            parking_notes=None,
            organizer_name=None,
            organizer_email=None,
            organizer_phone=None,
            application_url=None,
            application_contact=None,
            application_deadline_description=None,
            booth_rules=None,
            required_documents=None,
            notes=None,
            interest_level="watching",
        )
        refreshed = get_listing(listing.id)
        assert refreshed.name == "Updated Market Name"
        assert len(refreshed.booth_tiers) == 1
        assert refreshed.booth_tiers[0].label == "Single"


def test_archive_listing_sets_deleted_at(app):
    listing = _make_listing(app)
    with app.app_context():
        fetched = get_listing(listing.id)
        archive_listing(fetched, actor=None)
        archived = get_listing(listing.id)
        assert archived.deleted_at is not None


def test_book_from_catalog_copies_fields(app):
    listing = _make_listing(app)
    tier_id = None
    with app.app_context():
        fetched = get_listing(listing.id)
        tier_id = fetched.booth_tiers[0].id
    with app.app_context():
        market = book_from_catalog(
            listing.id,
            event_date=date(2026, 10, 17),
            booth_tier_id=tier_id,
            apply_corner_premium=True,
            status=MarketStatus.INTERESTED,
        )
        assert market.id is not None
        assert market.name == "Test Holiday Market"
        assert market.city == "Clarksville"
        assert market.state == "TN"
        assert market.power_available is True
        assert market.wifi_available is True
        assert market.food_available is True
        assert market.market_catalog_listing_id == listing.id
        assert market.status == MarketStatus.INTERESTED
        assert "10x10" in (market.booth_size or "")
        # 75 base + 25 corner premium = 100
        assert market.booth_fee == Decimal("100.00")


def test_book_from_catalog_archived_raises(app):
    listing = _make_listing(app)
    with app.app_context():
        fetched = get_listing(listing.id)
        archive_listing(fetched, actor=None)
    with app.app_context():
        try:
            book_from_catalog(listing.id, event_date=date(2026, 10, 17))
            assert False, "Expected ValueError"
        except ValueError:
            pass


def test_suggest_booking_dates_recurring(app):
    listing = _make_listing(app)
    with app.app_context():
        fetched = get_listing(listing.id)
        dates = suggest_booking_dates(fetched, today=date(2026, 8, 10), count=4)
        assert len(dates) == 4
        assert dates[0] == date(2026, 10, 17)


def test_sync_listing_occurrences_advances_past_date(app):
    listing = _make_listing(app)
    with app.app_context():
        fetched = get_listing(listing.id)
        # Force the next occurrence into the past.
        fetched.next_occurrence_date = date(2020, 1, 1)
        db.session.commit()
        changed = sync_listing_occurrences(fetched, today=date(2026, 8, 10))
        assert changed is True
        assert fetched.next_occurrence_date == date(2026, 10, 17)
        assert fetched.last_occurrence_date == date(2020, 1, 1)


def test_sync_listing_occurrences_idempotent(app):
    listing = _make_listing(app)
    with app.app_context():
        fetched = get_listing(listing.id)
        fetched.next_occurrence_date = date(2026, 10, 17)
        db.session.commit()
        changed = sync_listing_occurrences(fetched, today=date(2026, 8, 10))
        assert changed is False


def test_sync_replaces_corrupt_future_pointer(app):
    """A stored next_occurrence_date that the rule never produces must not
    block syncing. Otherwise the UI shows a wrong date and the Sync date
    button silently reports ``No change`` forever.
    """
    listing = _make_listing(app)
    with app.app_context():
        fetched = get_listing(listing.id)
        # Stash a date the demo rule (3rd Saturday of October) cannot generate.
        fetched.next_occurrence_date = date(2027, 1, 2)
        db.session.commit()
        changed = sync_listing_occurrences(fetched, today=date(2026, 8, 10))
        assert changed is True
        assert fetched.next_occurrence_date == date(2026, 10, 17)
