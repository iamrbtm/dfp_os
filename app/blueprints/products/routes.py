from __future__ import annotations

from dataclasses import dataclass

from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.blueprints.products import bp
from app.forms import CategoryForm, CollectionForm, ModelAssetForm, ProductForm, ProductVariantForm
from app.models import Category, Collection, ModelAsset, Product, ProductVariant, UserRole
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


def _bool_column(attr: str):
    return lambda item: "Yes" if getattr(item, attr) else "No"


PRODUCT_RESOURCES: dict[str, ResourceConfig] = {
    "products": ResourceConfig(
        key="products",
        singular="Product",
        plural="Products",
        model=Product,
        form_class=ProductForm,
        search_fields=["name", "slug", "sku_base"],
        columns=[
            ("Name", lambda item: item.name),
            ("Category", lambda item: item.category.name if item.category else "—"),
            ("Status", lambda item: item.status),
            ("Base Price", lambda item: item.base_price),
            ("Public", _bool_column("is_public")),
        ],
    ),
    "categories": ResourceConfig(
        key="categories",
        singular="Category",
        plural="Categories",
        model=Category,
        form_class=CategoryForm,
        search_fields=["name", "slug"],
        columns=[
            ("Name", lambda item: item.name),
            ("Slug", lambda item: item.slug),
            ("Public", _bool_column("is_public")),
            ("POS Visible", _bool_column("is_pos_visible")),
        ],
    ),
    "collections": ResourceConfig(
        key="collections",
        singular="Collection",
        plural="Collections",
        model=Collection,
        form_class=CollectionForm,
        search_fields=["name", "slug"],
        columns=[
            ("Name", lambda item: item.name),
            ("Slug", lambda item: item.slug),
            ("Public", _bool_column("is_public")),
            ("Sort Order", lambda item: item.sort_order),
        ],
    ),
    "variants": ResourceConfig(
        key="variants",
        singular="Variant",
        plural="Variants",
        model=ProductVariant,
        form_class=ProductVariantForm,
        search_fields=["name", "sku", "colorway"],
        columns=[
            ("Name", lambda item: item.name),
            ("Product", lambda item: item.product.name if item.product else "—"),
            ("SKU", lambda item: item.sku),
            ("Price", lambda item: item.price),
            ("Active", _bool_column("active")),
        ],
    ),
    "model-assets": ResourceConfig(
        key="model-assets",
        singular="Model Asset",
        plural="Model Assets",
        model=ModelAsset,
        form_class=ModelAssetForm,
        search_fields=["title", "designer_name", "license_type"],
        columns=[
            ("Title", lambda item: item.title),
            ("Source Type", lambda item: item.source_type),
            ("Linked Product", lambda item: item.product.name if item.product else "—"),
            ("Status", lambda item: item.status),
            ("Commercial Use", _bool_column("commercial_use_allowed")),
        ],
    ),
}


def _get_config(resource_key: str) -> ResourceConfig:
    return PRODUCT_RESOURCES[resource_key]


def _build_form(config: ResourceConfig, instance=None):
    if instance is None:
        return config.form_class()

    data = {}
    form = config.form_class()
    form.instance_id = instance.id
    for field_name, field in form._fields.items():
        if field_name in {"csrf_token", "submit"}:
            continue
        value = getattr(instance, field_name, None)
        if hasattr(value, "value"):
            value = value.value
        data[field_name] = value
    form = config.form_class(data=data)
    form.instance_id = instance.id
    return form


def _resource_endpoint_suffix(resource_key: str) -> str:
    return "" if resource_key == "products" else resource_key


@bp.get("/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def products_root():
    return redirect(url_for("products.list_resource", resource_key="products"))


@bp.route("/<resource_key>/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_resource(resource_key: str):
    if resource_key not in PRODUCT_RESOURCES:
        return render_template("errors/404.html"), 404

    config = _get_config(resource_key)
    page = request.args.get("page", default=1, type=int)
    search_term = request.args.get("q", "").strip()
    statement = select(config.model)
    if config.model is Product:
        statement = statement.where(Product.deleted_at.is_(None))
    statement = apply_search(statement, config.model, search_term, config.search_fields)
    pagination = paginate_query(statement.order_by(config.model.created_at.desc()), page, 20)
    rows = [
        {
            "id": item.id,
            "cells": [_display_value(getter(item)) for _, getter in config.columns],
        }
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
def create_resource(resource_key: str = "products"):
    if resource_key not in PRODUCT_RESOURCES:
        return render_template("errors/404.html"), 404

    config = _get_config(resource_key)
    form = config.form_class()
    if form.validate_on_submit():
        instance = config.model()
        form.apply(instance)
        try:
            save_instance(instance)
        except IntegrityError:
            flash(
                f"Unable to save that {config.singular.lower()}. Please check for duplicates.",
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
            url_for("products.detail_resource", resource_key=resource_key, resource_id=instance.id)
        )

    return render_template(
        "dashboard/resource_form.html", resource=config, form=form, mode="create"
    )


@bp.get("/<int:resource_id>")
@bp.get("/<resource_key>/<int:resource_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def detail_resource(resource_id: int, resource_key: str = "products"):
    if resource_key not in PRODUCT_RESOURCES:
        return render_template("errors/404.html"), 404

    config = _get_config(resource_key)
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404

    details = [
        {"label": label, "value": _display_value(getter(instance))}
        for label, getter in config.columns
    ]
    return render_template(
        "dashboard/resource_detail.html",
        resource=config,
        instance=instance,
        details=details,
    )


@bp.route("/<int:resource_id>/edit", methods=["GET", "POST"])
@bp.route("/<resource_key>/<int:resource_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def edit_resource(resource_id: int, resource_key: str = "products"):
    if resource_key not in PRODUCT_RESOURCES:
        return render_template("errors/404.html"), 404

    config = _get_config(resource_key)
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
                f"Unable to save that {config.singular.lower()}. Please check for duplicates.",
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
            url_for("products.detail_resource", resource_key=resource_key, resource_id=instance.id)
        )

    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="edit")


@bp.post("/<int:resource_id>/archive")
@bp.post("/<resource_key>/<int:resource_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def archive_resource_view(resource_id: int, resource_key: str = "products"):
    if resource_key not in PRODUCT_RESOURCES:
        return render_template("errors/404.html"), 404

    config = _get_config(resource_key)
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404

    archive_instance(instance)
    flash(f"{config.singular} archived.", "success")
    return redirect(url_for("products.list_resource", resource_key=resource_key))
