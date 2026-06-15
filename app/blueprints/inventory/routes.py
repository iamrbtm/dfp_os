from __future__ import annotations

from dataclasses import dataclass

from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.blueprints.inventory import bp
from app.forms import FilamentSpoolForm, InventoryLocationForm, InventoryRecordForm
from app.models import FilamentSpool, InventoryLocation, InventoryRecord, UserRole
from app.services.crud import (
    apply_search,
    archive_instance,
    get_by_id,
    paginate_query,
    save_instance,
)
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


def _display_value(value):
    if value is None or value == "":
        return "—"
    if hasattr(value, "value"):
        return value.value.replace("_", " ").title()
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


INVENTORY_RESOURCES: dict[str, ResourceConfig] = {
    "records": ResourceConfig(
        key="records",
        singular="Inventory Record",
        plural="Inventory Records",
        model=InventoryRecord,
        form_class=InventoryRecordForm,
        search_fields=[],
        columns=[
            ("Product", lambda item: item.product.name if item.product else "—"),
            ("Variant", lambda item: item.variant.name if item.variant else "—"),
            ("Location", lambda item: item.location.name if item.location else "—"),
            ("On Hand", lambda item: item.quantity_on_hand),
            ("Available", lambda item: item.quantity_available),
        ],
    ),
    "filament-spools": ResourceConfig(
        key="filament-spools",
        singular="Filament Spool",
        plural="Filament Spools",
        model=FilamentSpool,
        form_class=FilamentSpoolForm,
        search_fields=["brand", "material_type", "color_name"],
        columns=[
            ("Brand", lambda item: item.brand),
            ("Material", lambda item: item.material_type),
            ("Color", lambda item: item.color_name),
            ("Remaining (g)", lambda item: item.remaining_weight_grams),
            ("Status", lambda item: item.status),
        ],
    ),
    "locations": ResourceConfig(
        key="locations",
        singular="Inventory Location",
        plural="Inventory Locations",
        model=InventoryLocation,
        form_class=InventoryLocationForm,
        search_fields=["name", "type"],
        columns=[
            ("Name", lambda item: item.name),
            ("Type", lambda item: item.type),
            ("Active", lambda item: item.active),
            ("Description", lambda item: item.description),
        ],
    ),
}


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
def inventory_root():
    return redirect(url_for("inventory.list_resource", resource_key="records"))


@bp.route("/<resource_key>/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_resource(resource_key: str):
    if resource_key not in INVENTORY_RESOURCES:
        return render_template("errors/404.html"), 404
    config = INVENTORY_RESOURCES[resource_key]
    page = request.args.get("page", default=1, type=int)
    search_term = request.args.get("q", "").strip()
    statement = select(config.model)
    statement = apply_search(statement, config.model, search_term, config.search_fields)
    pagination = paginate_query(statement.order_by(config.model.created_at.desc()), page, 20)
    rows = [
        {"id": item.id, "cells": [_display_value(getter(item)) for _, getter in config.columns]}
        for item in pagination.items
    ]
    return render_template(
        "dashboard/resource_list.html",
        resource=config,
        rows=rows,
        columns=[label for label, _ in config.columns],
        pagination=pagination,
        search_term=search_term,
    )


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<resource_key>/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_resource(resource_key: str = "records"):
    if resource_key not in INVENTORY_RESOURCES:
        return render_template("errors/404.html"), 404
    config = INVENTORY_RESOURCES[resource_key]
    form = config.form_class()
    if form.validate_on_submit():
        instance = config.model()
        form.apply(instance)
        try:
            save_instance(instance)
        except IntegrityError:
            flash(
                f"Unable to save that {config.singular.lower()}. Please review duplicate values.",
                "danger",
            )
            return (
                render_template(
                    "dashboard/resource_form.html", resource=config, form=form, mode="create"
                ),
                400,
            )
        flash(f"{config.singular} created successfully.", "success")
        return redirect(
            url_for("inventory.detail_resource", resource_key=resource_key, resource_id=instance.id)
        )
    return render_template(
        "dashboard/resource_form.html", resource=config, form=form, mode="create"
    )


@bp.get("/<int:resource_id>")
@bp.get("/<resource_key>/<int:resource_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def detail_resource(resource_id: int, resource_key: str = "records"):
    if resource_key not in INVENTORY_RESOURCES:
        return render_template("errors/404.html"), 404
    config = INVENTORY_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    details = [
        {"label": label, "value": _display_value(getter(instance))}
        for label, getter in config.columns
    ]
    return render_template(
        "dashboard/resource_detail.html", resource=config, instance=instance, details=details
    )


@bp.route("/<int:resource_id>/edit", methods=["GET", "POST"])
@bp.route("/<resource_key>/<int:resource_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def edit_resource(resource_id: int, resource_key: str = "records"):
    if resource_key not in INVENTORY_RESOURCES:
        return render_template("errors/404.html"), 404
    config = INVENTORY_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    form = _build_form(config, instance)
    if form.validate_on_submit():
        form.apply(instance)
        try:
            save_instance(instance)
        except IntegrityError:
            flash(
                f"Unable to update that {config.singular.lower()}. Please review duplicate values.",
                "danger",
            )
            return (
                render_template(
                    "dashboard/resource_form.html", resource=config, form=form, mode="edit"
                ),
                400,
            )
        flash(f"{config.singular} updated successfully.", "success")
        return redirect(
            url_for("inventory.detail_resource", resource_key=resource_key, resource_id=instance.id)
        )
    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="edit")


@bp.post("/<int:resource_id>/archive")
@bp.post("/<resource_key>/<int:resource_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def archive_resource_view(resource_id: int, resource_key: str = "records"):
    if resource_key not in INVENTORY_RESOURCES:
        return render_template("errors/404.html"), 404
    config = INVENTORY_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    archive_instance(instance)
    flash(f"{config.singular} archived.", "success")
    return redirect(url_for("inventory.list_resource", resource_key=resource_key))
