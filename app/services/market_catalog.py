from __future__ import annotations

import re


from app.extensions import db
from app.models import (
    MarketCatalogBoothTier,
    MarketCatalogListing,
    MarketCategory,
    MarketInterestLevel,
)
from app.models.base import utc_now
from app.services.audit_client import get_audit_client
from app.services.market_catalog_recurrence import humanize_rrule


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    return _SLUG_RE.sub("-", value.strip().lower()).strip("-") or "listing"


def _unique_listing_slug(name: str, exclude_id: int | None = None) -> str:
    base = _slugify(name)
    candidate = base
    suffix = 1
    while True:
        query = db.session.query(MarketCatalogListing.id).filter(
            MarketCatalogListing.slug == candidate
        )
        if exclude_id is not None:
            query = query.filter(MarketCatalogListing.id != exclude_id)
        if not query.first():
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


def _unique_category_slug(name: str, exclude_id: int | None = None) -> str:
    base = _slugify(name)
    candidate = base
    suffix = 1
    while True:
        query = db.session.query(MarketCategory.id).filter(MarketCategory.slug == candidate)
        if exclude_id is not None:
            query = query.filter(MarketCategory.id != exclude_id)
        if not query.first():
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


def snapshot_listing(listing: MarketCatalogListing) -> dict:
    return {
        "name": listing.name,
        "slug": listing.slug,
        "category_id": listing.category_id,
        "is_recurring": listing.is_recurring,
        "rrule": listing.rrule,
        "interest_level": listing.interest_level.value if listing.interest_level else None,
        "city": listing.city,
        "state": listing.state,
        "next_occurrence_date": str(listing.next_occurrence_date)
        if listing.next_occurrence_date
        else None,
        "booth_tiers": [
            {
                "label": t.label,
                "price": str(t.price) if t.price is not None else None,
            }
            for t in listing.booth_tiers
        ],
    }


def snapshot_category(category: MarketCategory) -> dict:
    return {
        "name": category.name,
        "slug": category.slug,
        "sort_order": category.sort_order,
        "is_active": category.is_active,
    }


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------


def create_category(
    *, name: str, description: str | None = None, sort_order: int = 0, actor=None
) -> MarketCategory:
    category = MarketCategory(
        name=name.strip(),
        slug=_unique_category_slug(name),
        description=description,
        sort_order=sort_order,
        is_active=True,
    )
    db.session.add(category)
    db.session.commit()
    get_audit_client().record(
        action="market_category.created",
        entity_type="market_category",
        entity_id=str(category.id),
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        after_state=snapshot_category(category),
    )
    return category


def update_category(
    category: MarketCategory,
    *,
    name: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
    actor=None,
) -> MarketCategory:
    before = snapshot_category(category)
    if name is not None and name.strip() != category.name:
        category.name = name.strip()
        category.slug = _unique_category_slug(category.name, exclude_id=category.id)
    if description is not None:
        category.description = description
    if sort_order is not None:
        category.sort_order = sort_order
    if is_active is not None:
        category.is_active = is_active
    db.session.commit()
    get_audit_client().record(
        action="market_category.updated",
        entity_type="market_category",
        entity_id=str(category.id),
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        before_state=before,
        after_state=snapshot_category(category),
    )
    return category


def archive_category(category: MarketCategory, *, actor=None) -> MarketCategory:
    before = snapshot_category(category)
    category.deleted_at = utc_now()
    category.is_active = False
    db.session.commit()
    get_audit_client().record(
        action="market_category.archived",
        entity_type="market_category",
        entity_id=str(category.id),
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        before_state=before,
        after_state=snapshot_category(category),
    )
    return category


# ---------------------------------------------------------------------------
# Listing CRUD
# ---------------------------------------------------------------------------


def _apply_listing_fields(
    listing: MarketCatalogListing,
    *,
    name: str,
    category_id: int | None,
    description: str | None,
    website_url: str | None,
    location_name: str | None,
    address: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
    latitude: float | None,
    longitude: float | None,
    default_start_time,
    default_end_time,
    timezone: str | None,
    is_recurring: bool,
    rrule: str | None,
    recurrence_description: str | None,
    estimated_vendor_count: int | None,
    estimated_attendee_count: int | None,
    power_available: bool,
    wifi_available: bool,
    food_available: bool,
    restrooms_available: bool,
    indoor: bool,
    covered_outdoor: bool,
    outdoor: bool,
    parking_notes: str | None,
    organizer_name: str | None,
    organizer_email: str | None,
    organizer_phone: str | None,
    application_url: str | None,
    application_contact: str | None,
    application_deadline_description: str | None,
    booth_rules: str | None,
    required_documents: str | None,
    notes: str | None,
    interest_level: str | None,
    business_id: int | None,
) -> None:
    listing.name = name.strip()
    listing.category_id = category_id
    listing.description = description or None
    listing.website_url = website_url or None
    listing.location_name = location_name or None
    listing.address = address or None
    listing.city = city or None
    listing.state = state or None
    listing.zip_code = zip_code or None
    listing.latitude = latitude
    listing.longitude = longitude
    listing.default_start_time = default_start_time
    listing.default_end_time = default_end_time
    listing.timezone = timezone or "America/Chicago"
    listing.is_recurring = bool(is_recurring)
    listing.rrule = rrule or None
    listing.recurrence_description = recurrence_description or (
        humanize_rrule(rrule) if rrule else None
    )
    listing.estimated_vendor_count = estimated_vendor_count
    listing.estimated_attendee_count = estimated_attendee_count
    listing.power_available = bool(power_available)
    listing.wifi_available = bool(wifi_available)
    listing.food_available = bool(food_available)
    listing.restrooms_available = bool(restrooms_available)
    listing.indoor = bool(indoor)
    listing.covered_outdoor = bool(covered_outdoor)
    listing.outdoor = bool(outdoor)
    listing.parking_notes = parking_notes or None
    listing.organizer_name = organizer_name or None
    listing.organizer_email = organizer_email or None
    listing.organizer_phone = organizer_phone or None
    listing.application_url = application_url or None
    listing.application_contact = application_contact or None
    listing.application_deadline_description = application_deadline_description or None
    listing.booth_rules = booth_rules or None
    listing.required_documents = required_documents or None
    listing.notes = notes or None
    if interest_level:
        try:
            listing.interest_level = MarketInterestLevel(interest_level)
        except ValueError:
            listing.interest_level = MarketInterestLevel.WATCHING
    listing.business_id = business_id


def _replace_booth_tiers(listing: MarketCatalogListing, tiers: list[dict]) -> None:
    for existing in list(listing.booth_tiers):
        db.session.delete(existing)
    db.session.flush()
    for index, tier_data in enumerate(tiers):
        tier = MarketCatalogBoothTier(
            listing_id=listing.id,
            label=(tier_data.get("label") or "").strip() or "Booth",
            dimensions=tier_data.get("dimensions"),
            price=tier_data.get("price"),
            corner_premium=tier_data.get("corner_premium"),
            notes=tier_data.get("notes"),
            sort_order=tier_data.get("sort_order", index),
        )
        db.session.add(tier)


def create_listing(
    *, actor=None, tiers: list[dict] | None = None, **fields
) -> MarketCatalogListing:
    listing = MarketCatalogListing()
    listing.slug = _unique_listing_slug(fields.get("name") or "listing")
    _apply_listing_fields(listing, **fields)
    db.session.add(listing)
    db.session.flush()
    _replace_booth_tiers(listing, tiers or [])
    db.session.commit()
    get_audit_client().record(
        action="market_catalog.created",
        entity_type="market_catalog_listing",
        entity_id=str(listing.id),
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        after_state=snapshot_listing(listing),
    )
    return listing


def update_listing(
    listing: MarketCatalogListing,
    *,
    actor=None,
    tiers: list[dict] | None = None,
    **fields,
) -> MarketCatalogListing:
    before = snapshot_listing(listing)
    if "name" in fields and fields["name"]:
        listing.slug = _unique_listing_slug(fields["name"], exclude_id=listing.id)
    _apply_listing_fields(listing, **fields)
    if "name" in fields:
        listing.slug = _unique_listing_slug(fields["name"], exclude_id=listing.id)
    if tiers is not None:
        _replace_booth_tiers(listing, tiers)
    db.session.commit()
    get_audit_client().record(
        action="market_catalog.updated",
        entity_type="market_catalog_listing",
        entity_id=str(listing.id),
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        before_state=before,
        after_state=snapshot_listing(listing),
    )
    return listing


def archive_listing(listing: MarketCatalogListing, *, actor=None) -> MarketCatalogListing:
    before = snapshot_listing(listing)
    listing.deleted_at = utc_now()
    db.session.commit()
    get_audit_client().record(
        action="market_catalog.archived",
        entity_type="market_catalog_listing",
        entity_id=str(listing.id),
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        before_state=before,
        after_state=snapshot_listing(listing),
    )
    return listing


def restore_listing(listing: MarketCatalogListing, *, actor=None) -> MarketCatalogListing:
    before = snapshot_listing(listing)
    listing.deleted_at = None
    db.session.commit()
    get_audit_client().record(
        action="market_catalog.restored",
        entity_type="market_catalog_listing",
        entity_id=str(listing.id),
        actor_id=str(getattr(actor, "id", "")) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) if actor else None,
        source_module=__name__,
        before_state=before,
        after_state=snapshot_listing(listing),
    )
    return listing


def get_listing(listing_id: int) -> MarketCatalogListing | None:
    return db.session.get(MarketCatalogListing, listing_id)


def list_active_listings(category_id: int | None = None, interest_level: str | None = None):
    stmt = db.session.query(MarketCatalogListing).filter(MarketCatalogListing.deleted_at.is_(None))
    if category_id is not None:
        stmt = stmt.filter(MarketCatalogListing.category_id == category_id)
    if interest_level:
        try:
            stmt = stmt.filter(
                MarketCatalogListing.interest_level == MarketInterestLevel(interest_level)
            )
        except ValueError:
            pass
    return stmt.order_by(MarketCatalogListing.name.asc()).all()


def list_active_categories():
    return (
        db.session.query(MarketCategory)
        .filter(MarketCategory.deleted_at.is_(None))
        .order_by(MarketCategory.sort_order.asc(), MarketCategory.name.asc())
        .all()
    )
