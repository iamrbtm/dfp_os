from __future__ import annotations

from dataclasses import dataclass

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from markupsafe import escape
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.blueprints.markets import bp
from app.extensions import db
from app.forms import (
    MarketDocumentForm,
    MarketForm,
    MarketHotelBookingForm,
    MarketLogisticsForm,
    MarketPackingListForm,
    MarketTaskForm,
    MarketTimelineEventForm,
)
from app.models import (
    Market,
    MarketDocument,
    MarketDocumentType,
    MarketHotelBooking,
    MarketPackingList,
    MarketTask,
    MarketTimelineEvent,
    UserRole,
)
from app.services.admin_mutations import (
    archive_resource as archive_admin_resource,
    create_resource as create_admin_resource,
    snapshot_instance,
    update_resource as update_admin_resource,
)
from app.services.crud import apply_search, get_by_id, paginate_query
from app.services.markets import (
    complete_market_task,
    complete_timeline_event,
    fetch_weather_snapshot,
    geocode_market_address,
    get_market_command_center,
    get_market_performance,
    market_document_path,
    record_market_audit,
    save_market_document,
)
from app.services.storage import delete_storage_reference, send_storage_reference
from app.utils.auth import roles_required


@dataclass(frozen=True)
class ResourceConfig:
    key: str
    singular: str
    plural: str
    model: type
    form_class: type
    search_fields: list[str]
    columns: list[tuple[str, callable]]
    sortable_columns: dict[str, object]


def _display_value(value):
    if value is None or value == "":
        return "\u2014"
    if hasattr(value, "value"):
        return value.value.replace("_", " ").title()
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _format_money(value):
    if value is None:
        return "\u2014"
    return f"${value:,.2f}"


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _detail_forms(market: Market) -> dict:
    logistics_form = MarketLogisticsForm(obj=market)
    return {
        "logistics_form": logistics_form,
        "task_form": MarketTaskForm(),
        "timeline_form": MarketTimelineEventForm(),
        "hotel_form": MarketHotelBookingForm(),
        "document_form": MarketDocumentForm(),
        "packing_form": MarketPackingListForm(),
    }


def _render_market_section(market: Market, section: str):
    context = get_market_command_center(market)
    return render_template(
        f"markets/partials/_{section}.html",
        instance=market,
        market=market,
        command=context,
        **_detail_forms(market),
    )


def _after_market_action(market: Market, section: str, message: str, category: str = "success"):
    if _is_htmx():
        notice = (
            '<div class="mb-3 rounded-lg border p-3 text-sm" '
            'style="border-color: var(--color-border); color: var(--color-text);">'
            f"{escape(message)}</div>"
        )
        return notice + _render_market_section(market, section)
    flash(message, category)
    return redirect(url_for("markets.detail_resource", resource_id=market.id))


MARKET_RESOURCES: dict[str, ResourceConfig] = {
    "markets": ResourceConfig(
        key="markets",
        singular="Market",
        plural="Markets",
        model=Market,
        form_class=MarketForm,
        search_fields=["name", "location_name", "city", "state"],
        columns=[
            ("Name", lambda item: item.name),
            ("Location", lambda item: item.location_name or "\u2014"),
            ("Date", lambda item: item.event_date),
            ("Status", lambda item: item.status),
            ("Revenue", lambda item: _format_money(item.calculated_revenue)),
            ("Profit", lambda item: _format_money(item.calculated_profit)),
        ],
        sortable_columns={
            "name": Market.name,
            "location": Market.location_name,
            "date": Market.event_date,
            "status": Market.status,
            "created": Market.created_at,
        },
    ),
    "packing-lists": ResourceConfig(
        key="packing-lists",
        singular="Packing List Item",
        plural="Packing List",
        model=MarketPackingList,
        form_class=MarketPackingListForm,
        search_fields=["notes"],
        columns=[
            ("Product", lambda item: item.product.name if item.product else "\u2014"),
            ("Planned", lambda item: item.planned_quantity or 0),
            ("Packed", lambda item: item.packed_quantity or 0),
            ("Sold", lambda item: item.sold_quantity or 0),
            ("Returned", lambda item: item.returned_quantity or 0),
        ],
        sortable_columns={
            "product": MarketPackingList.product_id,
            "planned": MarketPackingList.planned_quantity,
            "packed": MarketPackingList.packed_quantity,
            "sold": MarketPackingList.sold_quantity,
            "returned": MarketPackingList.returned_quantity,
            "created": MarketPackingList.created_at,
        },
    ),
}


MARKET_SORT_LABELS = {
    "markets": {
        "Name": "name",
        "Location": "location",
        "Date": "date",
        "Status": "status",
    },
    "packing-lists": {
        "Product": "product",
        "Planned": "planned",
        "Packed": "packed",
        "Sold": "sold",
        "Returned": "returned",
    },
}


def _resolve_sort(config: ResourceConfig, resource_key: str) -> tuple[str, str, object]:
    sort_key = request.args.get("sort", "").strip().lower() or "created"
    sort_dir = request.args.get("dir", "").strip().lower() or "desc"
    if sort_key not in config.sortable_columns:
        sort_key = "created"
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"

    sort_column = config.sortable_columns[sort_key]
    order_clause = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
    return sort_key, sort_dir, order_clause


def _build_form(config: ResourceConfig, instance=None):
    if instance is None:
        return config.form_class()
    data = {}
    form = config.form_class()
    form.instance_id = instance.id
    for field_name in form._fields:
        if field_name in {"csrf_token", "submit"}:
            continue
        value = getattr(instance, field_name, None)
        if hasattr(value, "value"):
            value = value.value
        data[field_name] = value
    form = config.form_class(data=data)
    form.instance_id = instance.id
    return form


@bp.get("/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def markets_root():
    return redirect(url_for("markets.list_resource", resource_key="markets"))


@bp.route("/<resource_key>/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_resource(resource_key: str):
    if resource_key not in MARKET_RESOURCES:
        return render_template("errors/404.html"), 404
    config = MARKET_RESOURCES[resource_key]
    page = request.args.get("page", default=1, type=int)
    search_term = request.args.get("q", "").strip()
    sort_key, sort_dir, order_clause = _resolve_sort(config, resource_key)
    statement = apply_search(select(config.model), config.model, search_term, config.search_fields)
    pagination = paginate_query(statement.order_by(order_clause, config.model.id.desc()), page, 20)
    rows = [
        {"id": item.id, "cells": [_display_value(getter(item)) for _, getter in config.columns]}
        for item in pagination.items
    ]
    sortable_headers = []
    label_map = MARKET_SORT_LABELS.get(resource_key, {})
    for column in [label for label, _ in config.columns]:
        header_sort_key = label_map.get(column)
        if not header_sort_key:
            sortable_headers.append({"label": column, "sortable": False})
            continue
        next_dir = "desc" if sort_key == header_sort_key and sort_dir == "asc" else "asc"
        sortable_headers.append(
            {
                "label": column,
                "sortable": True,
                "sort_key": header_sort_key,
                "active": sort_key == header_sort_key,
                "dir": sort_dir if sort_key == header_sort_key else None,
                "next_dir": next_dir,
            }
        )
    return render_template(
        "dashboard/resource_list.html",
        resource=config,
        rows=rows,
        columns=[label for label, _ in config.columns],
        sortable_headers=sortable_headers,
        pagination=pagination,
        search_term=search_term,
        active_sort=sort_key,
        active_dir=sort_dir,
    )


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<resource_key>/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_resource(resource_key: str = "markets"):
    if resource_key not in MARKET_RESOURCES:
        return render_template("errors/404.html"), 404
    config = MARKET_RESOURCES[resource_key]
    form = config.form_class()
    if form.validate_on_submit():
        instance = config.model()
        form.apply(instance)
        try:
            if resource_key == "markets":
                geocode_market_address(instance, actor=current_user)
            create_admin_resource(instance, actor_id=current_user.id)
        except IntegrityError:
            db.session.rollback()
            flash(
                f"Unable to save that {config.singular.lower()}. Please review duplicate values.",
                "danger",
            )
            return render_template(
                "dashboard/resource_form.html", resource=config, form=form, mode="create"
            ), 400
        flash(f"{config.singular} created successfully.", "success")
        return redirect(url_for(
            "markets.detail_resource" if resource_key == "markets" else "markets.packing_list_detail",
            resource_key=resource_key,
            resource_id=instance.id,
        ))
    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="create")


@bp.get("/<int:resource_id>")
@bp.get("/<resource_key>/<int:resource_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def detail_resource(resource_id: int, resource_key: str = "markets"):
    if resource_key not in MARKET_RESOURCES:
        return render_template("errors/404.html"), 404
    config = MARKET_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    details = [
        {"label": label, "value": _display_value(getter(instance))}
        for label, getter in config.columns
    ]
    extra = None
    command = None
    forms = {}
    if resource_key == "markets":
        command = get_market_command_center(instance)
        extra = {"packing_list": command["packing_list"]}
        forms = _detail_forms(instance)
    return render_template(
        "markets/detail.html" if resource_key == "markets" else "dashboard/resource_detail.html",
        resource=config,
        instance=instance,
        details=details,
        extra=extra,
        command=command,
        **forms,
    )


@bp.route("/<int:resource_id>/edit", methods=["GET", "POST"])
@bp.route("/<resource_key>/<int:resource_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def edit_resource(resource_id: int, resource_key: str = "markets"):
    if resource_key not in MARKET_RESOURCES:
        return render_template("errors/404.html"), 404
    config = MARKET_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    form = _build_form(config, instance)
    if form.validate_on_submit():
        before_state = snapshot_instance(instance)
        form.apply(instance)
        try:
            if resource_key == "markets":
                geocode_market_address(instance, actor=current_user)
            update_admin_resource(instance, before_state=before_state, actor_id=current_user.id)
        except IntegrityError:
            db.session.rollback()
            flash(
                f"Unable to update that {config.singular.lower()}. Please review duplicate values.",
                "danger",
            )
            return render_template(
                "dashboard/resource_form.html", resource=config, form=form, mode="edit"
            ), 400
        flash(f"{config.singular} updated successfully.", "success")
        return redirect(url_for(
            "markets.detail_resource",
            resource_key=resource_key,
            resource_id=instance.id,
        ))
    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="edit")


@bp.post("/<int:resource_id>/archive")
@bp.post("/<resource_key>/<int:resource_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def archive_resource_view(resource_id: int, resource_key: str = "markets"):
    if resource_key not in MARKET_RESOURCES:
        return render_template("errors/404.html"), 404
    config = MARKET_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    archive_admin_resource(instance, actor_id=current_user.id)
    flash(f"{config.singular} archived.", "success")
    return redirect(url_for("markets.list_resource", resource_key=resource_key))


@bp.get("/<int:market_id>/performance")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def market_performance(market_id: int):
    market = get_by_id(Market, market_id)
    if market is None:
        return render_template("errors/404.html"), 404
    performance = get_market_performance(market)
    return render_template("markets/performance.html", market=market, performance=performance)


@bp.post("/<int:market_id>/logistics")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def update_logistics(market_id: int):
    market = get_by_id(Market, market_id)
    if market is None:
        return render_template("errors/404.html"), 404
    before = {
        "location_name": market.location_name,
        "zip_code": market.zip_code,
        "booth_location": market.booth_location,
        "latitude": market.latitude,
        "longitude": market.longitude,
    }
    form = MarketLogisticsForm()
    if form.validate_on_submit():
        form.apply(market)
        geocode_market_address(market, actor=current_user)
        db.session.commit()
        record_market_audit(
            "market.logistics_updated",
            "market",
            market.id,
            actor=current_user,
            before_state=before,
            after_state={
                "location_name": market.location_name,
                "zip_code": market.zip_code,
                "booth_location": market.booth_location,
                "latitude": market.latitude,
                "longitude": market.longitude,
            },
        )
        return _after_market_action(market, "event_logistics", "Market logistics updated.")
    return _after_market_action(market, "event_logistics", "Review the logistics fields.", "danger")


@bp.post("/<int:market_id>/tasks")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_task(market_id: int):
    market = get_by_id(Market, market_id)
    if market is None:
        return render_template("errors/404.html"), 404
    form = MarketTaskForm()
    if form.validate_on_submit():
        task = MarketTask(market_id=market.id)
        form.apply(task)
        db.session.add(task)
        db.session.commit()
        record_market_audit(
            "market_task.created",
            "market_task",
            task.id,
            actor=current_user,
            after_state={"market_id": market.id, "title": task.title, "task_type": task.task_type.value},
        )
        return _after_market_action(market, "tasks_marketing", "Task added.")
    return _after_market_action(market, "tasks_marketing", "Task title is required.", "danger")


@bp.post("/<int:market_id>/tasks/<int:task_id>/complete")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def complete_task(market_id: int, task_id: int):
    market = get_by_id(Market, market_id)
    task = get_by_id(MarketTask, task_id)
    if market is None or task is None or task.market_id != market.id:
        return render_template("errors/404.html"), 404
    complete_market_task(task, actor=current_user)
    return _after_market_action(market, "tasks_marketing", "Task completed.")


@bp.post("/<int:market_id>/timeline")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_timeline_event(market_id: int):
    market = get_by_id(Market, market_id)
    if market is None:
        return render_template("errors/404.html"), 404
    form = MarketTimelineEventForm()
    if form.validate_on_submit():
        event = MarketTimelineEvent(market_id=market.id)
        form.apply(event)
        db.session.add(event)
        db.session.commit()
        record_market_audit(
            "market_timeline.created",
            "market_timeline_event",
            event.id,
            actor=current_user,
            after_state={"market_id": market.id, "title": event.title, "event_type": event.event_type.value},
        )
        return _after_market_action(market, "schedule_timeline", "Timeline event added.")
    return _after_market_action(market, "schedule_timeline", "Timeline event title is required.", "danger")


@bp.post("/<int:market_id>/timeline/<int:event_id>/complete")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def complete_timeline(market_id: int, event_id: int):
    market = get_by_id(Market, market_id)
    event = get_by_id(MarketTimelineEvent, event_id)
    if market is None or event is None or event.market_id != market.id:
        return render_template("errors/404.html"), 404
    complete_timeline_event(event, actor=current_user)
    return _after_market_action(market, "schedule_timeline", "Timeline event completed.")


@bp.post("/<int:market_id>/hotels")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_hotel(market_id: int):
    market = get_by_id(Market, market_id)
    if market is None:
        return render_template("errors/404.html"), 404
    form = MarketHotelBookingForm()
    if form.validate_on_submit():
        booking = MarketHotelBooking(market_id=market.id)
        form.apply(booking)
        db.session.add(booking)
        db.session.commit()
        record_market_audit(
            "market_hotel.created",
            "market_hotel_booking",
            booking.id,
            actor=current_user,
            after_state={"market_id": market.id, "hotel_name": booking.hotel_name},
        )
        return _after_market_action(market, "travel", "Hotel booking added.")
    return _after_market_action(market, "travel", "Hotel name is required.", "danger")


@bp.post("/<int:market_id>/weather/fetch")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def fetch_weather(market_id: int):
    market = get_by_id(Market, market_id)
    if market is None:
        return render_template("errors/404.html"), 404
    try:
        fetch_weather_snapshot(market, actor=current_user)
    except ValueError as exc:
        return _after_market_action(market, "weather", str(exc), "warning")
    except Exception:
        return _after_market_action(
            market,
            "weather",
            "Weather.gov data could not be fetched right now. Existing snapshots were left unchanged.",
            "warning",
        )
    return _after_market_action(market, "weather", "Weather snapshot fetched.")


@bp.post("/<int:market_id>/documents")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def upload_document(market_id: int):
    market = get_by_id(Market, market_id)
    if market is None:
        return render_template("errors/404.html"), 404
    form = MarketDocumentForm()
    if form.validate_on_submit():
        try:
            save_market_document(
                market=market,
                file=request.files.get("file"),
                document_type=MarketDocumentType(form.document_type.data),
                notes=form.notes.data,
                uploaded_by_user_id=current_user.id,
                actor=current_user,
            )
        except ValueError as exc:
            return _after_market_action(market, "documents", str(exc), "danger")
        return _after_market_action(market, "documents", "Document uploaded.")
    return _after_market_action(market, "documents", "Document upload could not be validated.", "danger")


@bp.post("/<int:market_id>/documents/<int:document_id>/delete")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def delete_document(market_id: int, document_id: int):
    market = get_by_id(Market, market_id)
    document = get_by_id(MarketDocument, document_id)
    if market is None or document is None or document.market_id != market.id:
        return render_template("errors/404.html"), 404
    if document.stored_filename.startswith("s3://"):
        delete_storage_reference(document.stored_filename)
    else:
        path = market_document_path(document)
        if path.exists():
            path.unlink()
    record_market_audit(
        "market_document.deleted",
        "market_document",
        document.id,
        actor=current_user,
        before_state={"market_id": market.id, "filename": document.original_filename},
    )
    db.session.delete(document)
    db.session.commit()
    return _after_market_action(market, "documents", "Document deleted.")


@bp.get("/<int:market_id>/documents/<int:document_id>/download")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def download_document(market_id: int, document_id: int):
    market = get_by_id(Market, market_id)
    document = get_by_id(MarketDocument, document_id)
    if market is None or document is None or document.market_id != market.id:
        return render_template("errors/404.html"), 404
    if document.stored_filename.startswith("s3://"):
        return send_storage_reference(
            document.stored_filename,
            as_attachment=True,
            download_name=document.original_filename,
            mimetype=document.content_type,
        )
    path = market_document_path(document)
    if not path.exists():
        abort(404)
    return send_storage_reference(
        str(path),
        as_attachment=True,
        download_name=document.original_filename,
        mimetype=document.content_type,
    )


@bp.post("/<int:market_id>/packing-list/quick-add")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def packing_quick_add(market_id: int):
    market = get_by_id(Market, market_id)
    if market is None:
        return render_template("errors/404.html"), 404
    form = MarketPackingListForm()
    if form.validate_on_submit():
        item = MarketPackingList(market_id=market.id)
        form.apply(item)
        db.session.add(item)
        db.session.commit()
        record_market_audit(
            "market_packing_item.created",
            "market_packing_list",
            item.id,
            actor=current_user,
            after_state={"market_id": market.id, "product_id": item.product_id, "planned_quantity": item.planned_quantity},
        )
        return _after_market_action(market, "products_inventory", "Packing item added.")
    return _after_market_action(market, "products_inventory", "Choose a product before adding a packing item.", "danger")
