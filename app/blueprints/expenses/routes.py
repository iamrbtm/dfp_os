from __future__ import annotations

from dataclasses import dataclass

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.blueprints.expenses import bp
from app.forms import ExpenseForm
from app.models import Expense, UserRole
from app.services.crud import apply_search, get_by_id, paginate_query
from app.services.expenses import create_expense, snapshot_expense, update_expense, archive_expense
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
    if isinstance(value, float) or isinstance(value, int):
        return str(value)
    return str(value)


def _format_money(value):
    if value is None:
        return "\u2014"
    return f"${value:,.2f}"


EXPENSE_RESOURCES: dict[str, ResourceConfig] = {
    "expenses": ResourceConfig(
        key="expenses",
        singular="Expense",
        plural="Expenses",
        model=Expense,
        form_class=ExpenseForm,
        search_fields=["vendor", "description", "category"],
        columns=[
            ("Date", lambda item: item.date),
            ("Vendor", lambda item: item.vendor),
            ("Category", lambda item: item.category),
            ("Amount", lambda item: _format_money(item.amount)),
            ("Tax Deductible", lambda item: item.tax_deductible),
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
def expenses_root():
    return redirect(url_for("expenses.list_resource", resource_key="expenses"))


@bp.route("/<resource_key>/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_resource(resource_key: str):
    if resource_key not in EXPENSE_RESOURCES:
        return render_template("errors/404.html"), 404
    config = EXPENSE_RESOURCES[resource_key]
    page = request.args.get("page", default=1, type=int)
    search_term = request.args.get("q", "").strip()
    statement = apply_search(select(config.model), config.model, search_term, config.search_fields)
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
def create_resource(resource_key: str = "expenses"):
    if resource_key not in EXPENSE_RESOURCES:
        return render_template("errors/404.html"), 404
    config = EXPENSE_RESOURCES[resource_key]
    form = config.form_class()
    if form.validate_on_submit():
        instance = config.model()
        form.apply(instance)
        try:
            create_expense(instance, actor_id=current_user.id)
        except IntegrityError:
            from app.extensions import db
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
            "expenses.detail_resource",
            resource_key=resource_key,
            resource_id=instance.id,
        ))
    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="create")


@bp.get("/<int:resource_id>")
@bp.get("/<resource_key>/<int:resource_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def detail_resource(resource_id: int, resource_key: str = "expenses"):
    if resource_key not in EXPENSE_RESOURCES:
        return render_template("errors/404.html"), 404
    config = EXPENSE_RESOURCES[resource_key]
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
def edit_resource(resource_id: int, resource_key: str = "expenses"):
    if resource_key not in EXPENSE_RESOURCES:
        return render_template("errors/404.html"), 404
    config = EXPENSE_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    form = _build_form(config, instance)
    if form.validate_on_submit():
        before_state = snapshot_expense(instance)
        form.apply(instance)
        try:
            update_expense(instance, before_state=before_state, actor_id=current_user.id)
        except IntegrityError:
            from app.extensions import db
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
            "expenses.detail_resource",
            resource_key=resource_key,
            resource_id=instance.id,
        ))
    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="edit")


@bp.post("/<int:resource_id>/archive")
@bp.post("/<resource_key>/<int:resource_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def archive_resource_view(resource_id: int, resource_key: str = "expenses"):
    if resource_key not in EXPENSE_RESOURCES:
        return render_template("errors/404.html"), 404
    config = EXPENSE_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    archive_expense(instance, actor_id=current_user.id)
    flash(f"{config.singular} archived.", "success")
    return redirect(url_for("expenses.list_resource", resource_key=resource_key))
