from __future__ import annotations

from datetime import date
from decimal import Decimal

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
from app.services.business import get_default_business
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
from app.services.market_catalog_import import (
    extraction_to_listing_fields,
    generate_market_catalog_extraction,
    schema_file_exists,
)
from app.services.market_catalog_importers.registry import list_importers, run_importer
from app.services.market_catalog_recurrence import (
    build_rrule_from_wizard,
    humanize_rrule,
    next_two_occurrences,
    validate_rrule,
    wizard_state_from_listing,
    wizard_summary,
)
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
        market_catalog_ai_ready=bool(schema_file_exists()),
        importers=list_importers(),
    )


@bp.route("/listings/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_listing_view():
    form = MarketCatalogListingForm()
    if form.validate_on_submit():
        fields = _listing_fields(form)
        if fields["recurrence_error"]:
            flash(f"Recurrence error: {fields['recurrence_error']}", "danger")
            return render_template(
                "market_catalog/listing_form.html", form=form, mode="create"
            ), 400
        fields.pop("recurrence_error")
        tiers = _collect_tiers_from_form()
        listing = create_listing(actor=current_user, tiers=tiers, **fields)
        flash(f"Listing '{listing.name}' created.", "success")
        return redirect(url_for("market_catalog.detail_listing", listing_id=listing.id))
    return render_template("market_catalog/listing_form.html", form=form, mode="create")


@bp.post("/listings/import/ai")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def import_listing_ai_view():
    user_input = (request.form.get("ai_input") or "").strip()
    uploaded_file = request.files.get("ai_file")
    has_file = bool(uploaded_file and uploaded_file.filename)
    if not user_input and not has_file:
        flash("Add a URL, notes, prompt, or file before importing.", "danger")
        return redirect(url_for("market_catalog.list_listings"))
    try:
        payload = generate_market_catalog_extraction(
            user_input=user_input,
            uploaded_file=uploaded_file if has_file else None,
        )
        fields, tiers = extraction_to_listing_fields(payload)
        listing = create_listing(actor=current_user, tiers=tiers, **fields)
    except Exception as exc:
        flash(f"AI import failed: {exc}", "danger")
        return redirect(url_for("market_catalog.list_listings"))
    flash(f"Imported '{listing.name}' into the market catalog.", "success")
    return redirect(url_for("market_catalog.list_listings"))


@bp.post("/imports/<key>/run")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def run_import_view(key: str):
    """Run a registered web importer (dry-run by default, --commit via form)."""
    dry_run = request.form.get("commit") != "1"
    try:
        summary = run_importer(key, dry_run=dry_run, actor=current_user)
    except Exception as exc:  # surface Firecrawl/network/parse errors in the modal
        return (
            render_template(
                "market_catalog/_import_run_result.html",
                error=str(exc),
                key=key,
            ),
            200,
        )
    return render_template(
        "market_catalog/_import_run_result.html",
        summary=summary,
        key=key,
        dry_run=dry_run,
    )


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
    # Only derive the wizard sub-fields from the stored RRULE when this is a
    # GET. On POST (validation failure) the user's submitted formdata must win
    # so the wizard reflects what they actually entered.
    if request.method == "GET":
        _populate_wizard_from_listing(form, listing)
    if form.validate_on_submit():
        fields = _listing_fields(form)
        if fields["recurrence_error"]:
            flash(f"Recurrence error: {fields['recurrence_error']}", "danger")
            return render_template(
                "market_catalog/listing_form.html", form=form, mode="edit", listing=listing
            ), 400
        fields.pop("recurrence_error")
        tiers = _collect_tiers_from_form()
        update_listing(listing, actor=current_user, tiers=tiers, **fields)
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


@bp.post("/recurrence-preview")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def recurrence_preview():
    form = MarketCatalogListingForm(request.form)
    rrule, anchor_date, _is_recurring, error = _resolve_recurrence(form)
    if error:
        return jsonify({"error": error, "rrule": None, "human": "", "next_two": []}), 400
    wizard = form.wizard_data()
    if form.recurrence_override.data == "1":
        human = humanize_rrule(rrule)
    else:
        human = wizard_summary(
            pattern=wizard["pattern"],
            weekday=wizard["weekday"],
            nth=wizard["nth"],
            month=wizard["month"],
            day_of_month=wizard["day_of_month"],
            start_month=wizard["start_month"],
            end_month=wizard["end_month"],
            until_date=wizard["until_date"],
        )
    if not human:
        human = humanize_rrule(rrule) if rrule else "One-off market (no recurrence)."
    next_two = next_two_occurrences(rrule, dtstart=anchor_date)
    return jsonify(
        {
            "rrule": rrule,
            "dtstart": anchor_date.isoformat() if anchor_date else None,
            "human": human,
            "next_two": [d.isoformat() for d in next_two],
        }
    )


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


def _populate_wizard_from_listing(form, listing: MarketCatalogListing) -> None:
    """Server-side wizard prefill for edit pages.

    ``form(obj=listing)`` only populates fields whose name matches a model
    attribute. The wizard sub-fields (weekday, month, nth, ...) are virtual,
    so we derive them from the stored RRULE/anchor and assign them here so
    the correct tab opens and the inputs are correct even before JS runs.
    """
    state = wizard_state_from_listing(listing.rrule, listing.anchor_date)
    form.recurrence_pattern.data = state["recurrence_pattern"]
    form.recurrence_anchor.data = state["recurrence_anchor"]
    form.recurrence_until.data = state["recurrence_until"]
    form.recurrence_limit_months.data = state["recurrence_limit_months"]
    form.recurrence_weekday.data = state["recurrence_weekday"] or None
    form.recurrence_nth.data = state["recurrence_nth"]
    form.recurrence_month.data = state["recurrence_month"]
    form.recurrence_day.data = state["recurrence_day"]
    form.recurrence_start_month.data = state["recurrence_start_month"]
    form.recurrence_end_month.data = state["recurrence_end_month"]
    if listing.recurrence_description:
        form.recurrence_description.data = listing.recurrence_description


def _resolve_recurrence(form) -> tuple[str | None, date | None, bool, str | None]:
    """Build the RRULE + anchor date from the wizard payload.

    Returns ``(rrule, anchor_date, is_recurring, error)``. ``is_recurring`` is
    derived from the wizard result, not the form checkbox, so the stored
    flag always matches the recurrence configuration. If the user opened
    Advanced mode and typed a raw RRULE, that value wins over the generated one.
    """
    wizard = form.wizard_data()
    rrule, dtstart, error = build_rrule_from_wizard(**wizard)
    if error:
        return None, None, False, error
    is_recurring = wizard.get("pattern") != "one_off"
    if form.recurrence_override.data == "1":
        raw = (form.rrule.data or "").strip()
        if raw:
            valid, verr = validate_rrule(raw)
            if not valid:
                return None, None, False, verr
            rrule = raw
            is_recurring = bool(rrule)
    return rrule, dtstart or form.recurrence_anchor.data, is_recurring, None


def _recurrence_fields(form) -> dict:
    rrule, anchor_date, is_recurring, error = _resolve_recurrence(form)
    if error:
        return {
            "rrule": None,
            "recurrence_description": None,
            "anchor_date": None,
            "is_recurring": False,
            "recurrence_error": error,
        }
    wizard = form.wizard_data()
    summary = wizard_summary(
        pattern=wizard["pattern"],
        weekday=wizard["weekday"],
        nth=wizard["nth"],
        month=wizard["month"],
        day_of_month=wizard["day_of_month"],
        start_month=wizard["start_month"],
        end_month=wizard["end_month"],
        until_date=wizard["until_date"],
    )
    return {
        "rrule": rrule,
        "recurrence_description": summary,
        "anchor_date": anchor_date,
        "is_recurring": is_recurring,
        "recurrence_error": None,
    }


def _listing_fields(form):
    recurrence = _recurrence_fields(form)
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
    business = get_default_business()
    fields["business_id"] = business.id if business else None
    fields.update(recurrence)
    # recurrence fields include is_recurring; pop the error sentinel before save
    return fields


def _parse_money(value: str | None) -> "Decimal | None":
    from decimal import Decimal, InvalidOperation

    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


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
        tiers.append(
            {
                "label": label,
                "dimensions": (dims[i] or "").strip() or None if i < len(dims) else None,
                "price": _parse_money(prices[i] if i < len(prices) else None),
                "corner_premium": _parse_money(corners[i] if i < len(corners) else None),
                "notes": (notes[i] or "").strip() or None if i < len(notes) else None,
                "sort_order": int(sorts[i]) if i < len(sorts) and sorts[i] else i,
            }
        )
    return tiers
