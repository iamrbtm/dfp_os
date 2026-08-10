from __future__ import annotations

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from app.blueprints.market_catalog import bp
from app.extensions import db
from app.forms.market_catalog import (
    BookFromCatalogForm,
    MarketCatalogListingForm,
    MarketCategoryForm,
)
from app.models import (
    MarketCatalogListing,
    MarketCategory,
    MarketInterestLevel,
    UserRole,
)
from app.services.crud import apply_search, get_by_id, paginate_query
from app.services.market_catalog import (
    archive_category,
    archive_listing,
    create_category,
    create_listing,
    get_listing,
    list_active_categories,
    restore_listing,
    update_category,
    update_listing,
)
from app.services.market_catalog_booking import book_from_catalog, suggest_booking_dates
from app.services.market_catalog_recurrence import humanize_rrule, validate_rrule
from app.services.market_catalog_sync import sync_listing_occurrences
from app.utils.auth import roles_required


def _format_date(value):
    if value is None:
        return "—"
    return value.strftime("%b %d, %Y")


def _format_time(value):
    if value is None:
        return "—"
    return value.strftime("%I:%M %p")


def _format_money(value):
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _pill(value):
    if value is None or value == "":
        return "—"
    if hasattr(value, "value"):
        return value.value.replace("_", " ").title()
    return str(value)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@bp.get("/categories")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_categories():
    categories = list_active_categories()
    listing_counts = {
        row[0]: row[1]
        for row in db.session.query(
            MarketCatalogListing.category_id,
            db.func.count(MarketCatalogListing.id),
        )
        .filter(MarketCatalogListing.deleted_at.is_(None))
        .group_by(MarketCatalogListing.category_id)
        .all()
    }
    return render_template(
        "market_catalog/categories.html",
        categories=categories,
        listing_counts=listing_counts,
    )


@bp.route("/categories/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN)
def create_category_view():
    form = MarketCategoryForm()
    if form.validate_on_submit():
        category = create_category(
            name=form.name.data,
            description=form.description.data,
            sort_order=form.sort_order.data or 0,
            actor=current_user,
        )
        flash(f"Category '{category.name}' created.", "success")
        return redirect(url_for("market_catalog.list_categories"))
    return render_template("market_catalog/category_form.html", form=form, mode="create")


@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN)
def edit_category_view(category_id: int):
    category = get_by_id(MarketCategory, category_id)
    if category is None or category.deleted_at is not None:
        return render_template("errors/404.html"), 404
    form = MarketCategoryForm(obj=category)
    if form.validate_on_submit():
        update_category(
            category,
            name=form.name.data,
            description=form.description.data,
            sort_order=form.sort_order.data or 0,
            is_active=bool(form.is_active.data),
            actor=current_user,
        )
        flash("Category updated.", "success")
        return redirect(url_for("market_catalog.list_categories"))
    return render_template(
        "market_catalog/category_form.html", form=form, mode="edit", category=category
    )


@bp.post("/categories/<int:category_id>/archive")
@roles_required(UserRole.ADMIN)
def archive_category_view(category_id: int):
    category = get_by_id(MarketCategory, category_id)
    if category is None or category.deleted_at is not None:
        return render_template("errors/404.html"), 404
    archive_category(category, actor=current_user)
    flash("Category archived.", "success")
    return redirect(url_for("market_catalog.list_categories"))


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------


@bp.get("/")
@bp.get("/listings")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_listings():
    page = request.args.get("page", default=1, type=int)
    search_term = request.args.get("q", "").strip()
    category_filter = request.args.get("category", type=int)
    interest_filter = request.args.get("interest", "").strip()
    archived = request.args.get("archived", "").strip() == "1"

    stmt = select(MarketCatalogListing)
    if not archived:
        stmt = stmt.where(MarketCatalogListing.deleted_at.is_(None))
    else:
        stmt = stmt.where(MarketCatalogListing.deleted_at.is_not(None))
    stmt = apply_search(
        stmt,
        MarketCatalogListing,
        search_term,
        ["name", "city", "state", "location_name", "organizer_name"],
    )
    if category_filter:
        stmt = stmt.where(MarketCatalogListing.category_id == category_filter)
    if interest_filter:
        try:
            stmt = stmt.where(
                MarketCatalogListing.interest_level == MarketInterestLevel(interest_filter)
            )
        except ValueError:
            pass
    stmt = stmt.order_by(
        MarketCatalogListing.next_occurrence_date.asc().nullslast(), MarketCatalogListing.name.asc()
    )
    pagination = paginate_query(stmt, page, 20)
    categories = list_active_categories()
    return render_template(
        "market_catalog/listings.html",
        listings=pagination.items,
        pagination=pagination,
        search_term=search_term,
        categories=categories,
        category_filter=category_filter,
        interest_filter=interest_filter,
        archived=archived,
    )


@bp.route("/listings/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_listing_view():
    form = MarketCatalogListingForm()
    if form.validate_on_submit():
        valid, error = validate_rrule(form.rrule.data)
        if not valid:
            flash(f"RRULE error: {error}", "danger")
            return render_template(
                "market_catalog/listing_form.html", form=form, mode="create"
            ), 400
        tiers = _collect_tiers_from_form()
        listing = create_listing(actor=current_user, tiers=tiers, **_listing_fields(form))
        flash(f"Listing '{listing.name}' created.", "success")
        return redirect(url_for("market_catalog.detail_listing", listing_id=listing.id))
    return render_template("market_catalog/listing_form.html", form=form, mode="create")


@bp.get("/listings/<int:listing_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def detail_listing(listing_id: int):
    listing = get_listing(listing_id)
    if listing is None or listing.deleted_at is not None:
        return render_template("errors/404.html"), 404
    occurrences = suggest_booking_dates(listing, count=4)
    booked_markets = list(listing.booked_markets)
    form = BookFromCatalogForm(listing=listing)
    return render_template(
        "market_catalog/detail.html",
        listing=listing,
        occurrences=occurrences,
        booked_markets=booked_markets,
        booking_form=form,
        humanize=humanize_rrule,
        format_date=_format_date,
        format_time=_format_time,
        format_money=_format_money,
        pill=_pill,
    )


@bp.route("/listings/<int:listing_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def edit_listing_view(listing_id: int):
    listing = get_listing(listing_id)
    if listing is None or listing.deleted_at is not None:
        return render_template("errors/404.html"), 404
    form = MarketCatalogListingForm(obj=listing)
    if form.validate_on_submit():
        valid, error = validate_rrule(form.rrule.data)
        if not valid:
            flash(f"RRULE error: {error}", "danger")
            return render_template(
                "market_catalog/listing_form.html", form=form, mode="edit", listing=listing
            ), 400
        tiers = _collect_tiers_from_form()
        update_listing(listing, actor=current_user, tiers=tiers, **_listing_fields(form))
        flash("Listing updated.", "success")
        return redirect(url_for("market_catalog.detail_listing", listing_id=listing.id))
    return render_template(
        "market_catalog/listing_form.html", form=form, mode="edit", listing=listing
    )


@bp.post("/listings/<int:listing_id>/archive")
@roles_required(UserRole.ADMIN)
def archive_listing_view(listing_id: int):
    listing = get_listing(listing_id)
    if listing is None or listing.deleted_at is not None:
        return render_template("errors/404.html"), 404
    archive_listing(listing, actor=current_user)
    flash("Listing archived.", "success")
    return redirect(url_for("market_catalog.list_listings"))


@bp.post("/listings/<int:listing_id>/restore")
@roles_required(UserRole.ADMIN)
def restore_listing_view(listing_id: int):
    listing = get_listing(listing_id)
    if listing is None or listing.deleted_at is None:
        return render_template("errors/404.html"), 404
    restore_listing(listing, actor=current_user)
    flash("Listing restored.", "success")
    return redirect(url_for("market_catalog.detail_listing", listing_id=listing.id))


@bp.post("/listings/<int:listing_id>/sync")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sync_listing_view(listing_id: int):
    listing = get_listing(listing_id)
    if listing is None or listing.deleted_at is not None:
        return render_template("errors/404.html"), 404
    changed = sync_listing_occurrences(listing, actor=current_user)
    if changed:
        flash(f"Next occurrence updated to {listing.next_occurrence_date}.", "success")
    else:
        flash("No change — occurrence is still current.", "info")
    return redirect(url_for("market_catalog.detail_listing", listing_id=listing.id))


@bp.get("/listings/<int:listing_id>/occurrences")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def listing_occurrences(listing_id: int):
    listing = get_listing(listing_id)
    if listing is None or listing.deleted_at is not None:
        return jsonify({"error": "not_found"}), 404
    occurrences = suggest_booking_dates(listing, count=6)
    return jsonify({"occurrences": [d.isoformat() for d in occurrences]})


# ---------------------------------------------------------------------------
# Book it
# ---------------------------------------------------------------------------


@bp.route("/listings/<int:listing_id>/book", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def book_listing(listing_id: int):
    listing = get_listing(listing_id)
    if listing is None or listing.deleted_at is not None:
        return render_template("errors/404.html"), 404
    form = BookFromCatalogForm(listing=listing)
    suggested = suggest_booking_dates(listing, count=4)
    if request.method == "GET" and suggested and not form.event_date.data:
        form.event_date.data = suggested[0]
    if form.validate_on_submit():
        from app.models import MarketStatus

        try:
            market = book_from_catalog(
                listing.id,
                event_date=form.event_date.data,
                booth_tier_id=form.booth_tier_id.data,
                apply_corner_premium=bool(form.apply_corner_premium.data),
                status=MarketStatus(form.status.data),
                actor=current_user,
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("market_catalog.detail_listing", listing_id=listing.id))
        flash(f"Booked '{listing.name}' for {form.event_date.data}.", "success")
        return redirect(url_for("markets.detail_resource", resource_id=market.id))
    return render_template(
        "market_catalog/book.html",
        listing=listing,
        form=form,
        suggested_dates=suggested,
        format_date=_format_date,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _listing_fields(form):
    fields = {}
    for name in (
        "name",
        "category_id",
        "description",
        "website_url",
        "location_name",
        "address",
        "city",
        "state",
        "zip_code",
        "default_start_time",
        "default_end_time",
        "timezone",
        "is_recurring",
        "rrule",
        "recurrence_description",
        "estimated_vendor_count",
        "estimated_attendee_count",
        "power_available",
        "wifi_available",
        "food_available",
        "restrooms_available",
        "indoor",
        "covered_outdoor",
        "outdoor",
        "parking_notes",
        "organizer_name",
        "organizer_email",
        "organizer_phone",
        "application_url",
        "application_contact",
        "application_deadline_description",
        "booth_rules",
        "required_documents",
        "notes",
        "interest_level",
    ):
        fields[name] = getattr(form, name).data
    fields["latitude"] = float(form.latitude.data) if form.latitude.data is not None else None
    fields["longitude"] = float(form.longitude.data) if form.longitude.data is not None else None
    return fields


def _collect_tiers_from_form() -> list[dict]:
    raw = request.form.to_dict(flat=False)
    tiers = []
    labels = raw.get("tier_label", [])
    dims = raw.get("tier_dimensions", [])
    prices = raw.get("tier_price", [])
    corners = raw.get("tier_corner", [])
    notes = raw.get("tier_notes", [])
    sorts = raw.get("tier_sort", [])
    for i in range(len(labels)):
        label = (labels[i] or "").strip()
        if not label:
            continue
        try:
            price = prices[i] if i < len(prices) else None
        except IndexError, ValueError:
            price = None
        try:
            corner = corners[i] if i < len(corners) else None
        except IndexError, ValueError:
            corner = None
        tiers.append(
            {
                "label": label,
                "dimensions": dims[i] if i < len(dims) else None,
                "price": price,
                "corner_premium": corner,
                "notes": notes[i] if i < len(notes) else None,
                "sort_order": int(sorts[i]) if i < len(sorts) and sorts[i] else i,
            }
        )
    return tiers
