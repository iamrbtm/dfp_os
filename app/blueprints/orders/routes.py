from __future__ import annotations

from dataclasses import dataclass

from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.blueprints.orders import bp
from app.extensions import db
from app.forms import OrderForm, OrderItemForm, PaymentForm
from app.models import Order, OrderItem, Payment, UserRole
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
        return "\u2014"
    if hasattr(value, "value"):
        return value.value.replace("_", " ").title()
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


ORDER_RESOURCES: dict[str, ResourceConfig] = {
    "orders": ResourceConfig(
        key="orders",
        singular="Order",
        plural="Orders",
        model=Order,
        form_class=OrderForm,
        search_fields=["order_number"],
        columns=[
            ("Order #", lambda item: item.order_number),
            ("Customer", lambda item: item.customer.full_name if item.customer else "\u2014"),
            ("Status", lambda item: item.status),
            ("Total", lambda item: item.total),
            ("Paid", lambda item: item.paid_amount),
        ],
    ),
    "items": ResourceConfig(
        key="items",
        singular="Order Item",
        plural="Order Items",
        model=OrderItem,
        form_class=OrderItemForm,
        search_fields=[],
        columns=[
            ("Order", lambda item: item.order.order_number if item.order else "\u2014"),
            ("Product", lambda item: item.product.name if item.product else "\u2014"),
            ("Qty", lambda item: item.quantity),
            ("Unit Price", lambda item: item.unit_price),
            ("Line Total", lambda item: item.line_total),
        ],
    ),
    "payments": ResourceConfig(
        key="payments",
        singular="Payment",
        plural="Payments",
        model=Payment,
        form_class=PaymentForm,
        search_fields=[],
        columns=[
            ("Order", lambda item: item.order.order_number if item.order else "\u2014"),
            ("Amount", lambda item: item.amount),
            ("Method", lambda item: item.method),
            ("Date", lambda item: item.payment_date.strftime("%Y-%m-%d") if item.payment_date else "\u2014"),
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
def orders_root():
    return redirect(url_for("orders.list_resource", resource_key="orders"))


@bp.route("/<resource_key>/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_resource(resource_key: str):
    if resource_key not in ORDER_RESOURCES:
        return render_template("errors/404.html"), 404
    config = ORDER_RESOURCES[resource_key]
    page = request.args.get("page", default=1, type=int)
    search_term = request.args.get("q", "").strip()
    statement = select(config.model)
    if config.model is Order:
        statement = statement.where(Order.deleted_at.is_(None))
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
def create_resource(resource_key: str = "orders"):
    if resource_key not in ORDER_RESOURCES:
        return render_template("errors/404.html"), 404
    config = ORDER_RESOURCES[resource_key]
    form = config.form_class()
    if form.validate_on_submit():
        instance = config.model()
        form.apply(instance)
        try:
            save_instance(instance)
        except IntegrityError:
            flash(f"Unable to save that {config.singular.lower()}.", "danger")
            return (
                render_template(
                    "dashboard/resource_form.html", resource=config, form=form, mode="create"
                ),
                400,
            )
        flash(f"{config.singular} created successfully.", "success")
        return redirect(
            url_for("orders.detail_resource", resource_key=resource_key, resource_id=instance.id)
        )
    return render_template(
        "dashboard/resource_form.html", resource=config, form=form, mode="create"
    )


@bp.get("/<int:resource_id>")
@bp.get("/<resource_key>/<int:resource_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def detail_resource(resource_id: int, resource_key: str = "orders"):
    if resource_key not in ORDER_RESOURCES:
        return render_template("errors/404.html"), 404
    config = ORDER_RESOURCES[resource_key]
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
def edit_resource(resource_id: int, resource_key: str = "orders"):
    if resource_key not in ORDER_RESOURCES:
        return render_template("errors/404.html"), 404
    config = ORDER_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    form = _build_form(config, instance)
    if form.validate_on_submit():
        form.apply(instance)
        try:
            save_instance(instance)
        except IntegrityError:
            flash(f"Unable to update that {config.singular.lower()}.", "danger")
            return (
                render_template(
                    "dashboard/resource_form.html", resource=config, form=form, mode="edit"
                ),
                400,
            )
        flash(f"{config.singular} updated successfully.", "success")
        return redirect(
            url_for("orders.detail_resource", resource_key=resource_key, resource_id=instance.id)
        )
    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="edit")


@bp.post("/<int:resource_id>/archive")
@bp.post("/<resource_key>/<int:resource_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def archive_resource_view(resource_id: int, resource_key: str = "orders"):
    if resource_key not in ORDER_RESOURCES:
        return render_template("errors/404.html"), 404
    config = ORDER_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    if config.model is Order:
        archive_instance(instance)
    elif config.model is Payment:
        archive_instance(instance)
    elif config.model is OrderItem:
        db.session.delete(instance)
        db.session.commit()
    flash(f"{config.singular} archived.", "success")
    return redirect(url_for("orders.list_resource", resource_key=resource_key))
