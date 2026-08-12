from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models import Market, MarketCatalogListing, MarketStatus
from app.services.audit_client import get_audit_client
from app.services.market_catalog import get_listing
from app.services.market_catalog_recurrence import next_occurrences, parse_rrule


def suggest_booking_dates(
    listing: MarketCatalogListing, today: date | None = None, count: int = 4
) -> list[date]:
    if listing is None or listing.deleted_at is not None:
        return []
    anchor = today or date.today()
    if not listing.is_recurring or not listing.rrule:
        candidate = listing.next_occurrence_date or listing.anchor_date
        if candidate and candidate >= anchor:
            return [candidate]
        return []
    rrule_obj = parse_rrule(listing.rrule)
    if rrule_obj is None:
        return []
    return next_occurrences(rrule_obj, after_date=anchor, count=count)


def book_from_catalog(
    listing_id: int,
    *,
    event_date: date,
    booth_tier_id: int | None = None,
    apply_corner_premium: bool = False,
    status: MarketStatus = MarketStatus.INTERESTED,
    actor=None,
) -> Market:
    listing = get_listing(listing_id)
    if listing is None or listing.deleted_at is not None:
        raise ValueError("That catalog listing no longer exists.")

    market = Market()
    market.name = listing.name
    market.location_name = listing.location_name
    market.address = listing.address
    market.city = listing.city
    market.state = listing.state
    market.zip_code = listing.zip_code
    market.latitude = listing.latitude
    market.longitude = listing.longitude
    market.event_date = event_date
    market.start_time = listing.default_start_time
    market.end_time = listing.default_end_time
    market.power_available = listing.power_available
    market.wifi_available = listing.wifi_available
    market.food_available = listing.food_available
    market.application_url = listing.application_url
    market.application_contact = listing.application_contact
    market.booth_rules = listing.booth_rules
    market.required_documents = listing.required_documents
    market.notes = listing.notes
    market.market_catalog_listing_id = listing.id
    market.status = status

    # Booth tier → Market.booth_size + booth_fee
    selected_tier = None
    if booth_tier_id is not None:
        selected_tier = next((t for t in listing.booth_tiers if t.id == booth_tier_id), None)
    if selected_tier is None and listing.booth_tiers:
        selected_tier = listing.booth_tiers[0]

    if selected_tier is not None:
        size_label = selected_tier.label
        if selected_tier.dimensions:
            size_label = f"{selected_tier.label} ({selected_tier.dimensions})"
        market.booth_size = size_label
        price = selected_tier.price
        if price is not None and apply_corner_premium and selected_tier.corner_premium is not None:
            price = price + selected_tier.corner_premium
        market.booth_fee = price

    db.session.add(market)
    db.session.flush()

    # Geocode if lat/long missing
    if market.latitude is None or market.longitude is None:
        try:
            from app.services.markets import geocode_market_address

            geocode_market_address(market, actor=actor)
        except Exception:
            pass

    db.session.commit()

    get_audit_client().record(
        action="market_catalog.booked",
        entity_type="market_catalog_listing",
        entity_id=str(listing.id),
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        after_state={
            "listing_id": listing.id,
            "market_id": market.id,
            "event_date": str(event_date),
            "booth_tier_id": booth_tier_id,
            "status": status.value,
        },
    )
    return market
