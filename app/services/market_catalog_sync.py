from __future__ import annotations

from datetime import date

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
    anchor_date = today or date.today()

    # One-off market: surface the anchor date as the next occurrence, but never
    # advance it (a one-off only happens once).
    if not listing.is_recurring:
        if listing.anchor_date and listing.next_occurrence_date != listing.anchor_date:
            before = listing.next_occurrence_date
            listing.next_occurrence_date = listing.anchor_date
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
                before_state={"next_occurrence_date": str(before) if before else None},
                after_state={
                    "next_occurrence_date": str(listing.anchor_date)
                    if listing.anchor_date
                    else None
                },
            )
            return True
        return False

    if not listing.rrule:
        return False

    rrule_obj = parse_rrule(listing.rrule)
    if rrule_obj is None:
        return False

    # The stored ``next_occurrence_date`` is only trusted if it matches the
    # rule's true next occurrence from today. A future date that the rule
    # never produces (e.g. a leftover Saturday pointer for a Wednesday-only
    # rule, or a value seeded from a stale demo) would otherwise block this
    # sync forever while still showing a wrong date to the user.
    expected_next = next_occurrence(rrule_obj, after_date=anchor_date)
    if expected_next is None:
        return False
    if (
        listing.next_occurrence_date is not None
        and listing.next_occurrence_date >= anchor_date
        and listing.next_occurrence_date == expected_next
    ):
        return False

    # Stored value is missing, stale, or corrupt. Advance to the rule's
    # true next occurrence from today (never moves the pointer backwards).
    before_state = {
        "next_occurrence_date": str(listing.next_occurrence_date)
        if listing.next_occurrence_date
        else None,
        "last_occurrence_date": str(listing.last_occurrence_date)
        if listing.last_occurrence_date
        else None,
    }
    new_next = expected_next
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
