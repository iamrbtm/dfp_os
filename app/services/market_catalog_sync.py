from __future__ import annotations

from datetime import date, timezone

from app.extensions import db
from app.models import MarketCatalogListing
from app.models.base import utc_now
from app.services.audit_client import get_audit_client
from app.services.market_catalog_recurrence import next_occurrence, parse_rrule


def sync_listing_occurrences(
    listing: MarketCatalogListing,
    today: date | None = None,
    actor=None,
) -> bool:
    if not listing.is_recurring or not listing.rrule:
        return False

    rrule_obj = parse_rrule(listing.rrule)
    if rrule_obj is None:
        return False

    anchor_date = today or date.today()
    boundary_date = listing.next_occurrence_date or anchor_date

    # Only advance if the stored next occurrence is in the past (or today).
    if listing.next_occurrence_date is not None and listing.next_occurrence_date > anchor_date:
        return False

    new_next = next_occurrence(rrule_obj, after_date=boundary_date)
    if new_next is None:
        return False

    # Never move the pointer backwards.
    if (
        listing.next_occurrence_date is not None
        and new_next <= listing.next_occurrence_date
    ):
        return False

    before_state = {
        "next_occurrence_date": str(listing.next_occurrence_date)
        if listing.next_occurrence_date
        else None,
        "last_occurrence_date": str(listing.last_occurrence_date)
        if listing.last_occurrence_date
        else None,
    }

    listing.last_occurrence_date = listing.next_occurrence_date
    listing.next_occurrence_date = new_next
    listing.last_synced_at = utc_now()
    db.session.commit()

    get_audit_client().record(
        action="market_catalog.occurrence_advanced",
        entity_type="market_catalog_listing",
        entity_id=str(listing.id),
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        before_state=before_state,
        after_state={
            "next_occurrence_date": str(new_next),
            "last_occurrence_date": str(listing.last_occurrence_date)
            if listing.last_occurrence_date
            else None,
        },
    )
    return True


def sync_all_listings(today: date | None = None, actor=None) -> int:
    anchor = today or date.today()
    listings = (
        db.session.query(MarketCatalogListing)
        .filter(
            MarketCatalogListing.is_recurring.is_(True),
            MarketCatalogListing.rrule.is_not(None),
            MarketCatalogListing.deleted_at.is_(None),
        )
        .all()
    )
    advanced = 0
    for listing in listings:
        if sync_listing_occurrences(listing, today=anchor, actor=actor):
            advanced += 1
    return advanced