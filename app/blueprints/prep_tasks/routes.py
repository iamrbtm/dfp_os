from __future__ import annotations

from dataclasses import dataclass

from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import select

from app.blueprints.prep_tasks import bp
from app.forms.admin import PrepTaskAdminForm, PrepTaskTemplateForm
from app.models import PrepTask, PrepTaskTemplate, UserRole
from app.services.crud import apply_search, archive_instance, get_by_id, paginate_query, save_instance
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
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


RESOURCES = {
    "templates": ResourceConfig(
        key="templates",
        singular="Prep Task Template",
        plural="Prep Task Templates",
        model=PrepTaskTemplate,
        form_class=PrepTaskTemplateForm,
        search_fields=["title", "description"],
        columns=[
            ("Title", lambda item: item.title),
            ("Category", lambda item: item.category),
            ("Days Before", lambda item: item.default_due_days_before),
            ("Enabled", lambda item: item.default_enabled),
        ],
    ),
    "tasks": ResourceConfig(
        key="tasks",
        singular="Prep Task",
        plural="Prep Tasks",
        model=PrepTask,
        form_class=PrepTaskAdminForm,
        search_fields=["title", "notes", "source"],
        columns=[
            ("Title", lambda item: item.title),
            ("Category", lambda item: item.category),
            ("Status", lambda item: item.status),
            ("Market", lambda item: item.market.name if item.market else None),
            ("Due", lambda item: item.due_at),
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
def root():
    return redirect(url_for("prep_tasks.list_resource", resource_key="tasks"))


@bp.get("/<resource_key>/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_resource(resource_key: str):
    config = RESOURCES.get(resource_key)
    if config is None:
        return render_template("errors/404.html"), 404
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    statement = apply_search(select(config.model), config.model, q, config.search_fields)
    pagination = paginate_query(statement.order_by(config.model.created_at.desc()), page, 20)
    rows = [{"id": item.id, "cells": [_display_value(getter(item)) for _, getter in config.columns]} for item in pagination.items]
    return render_template(
        "dashboard/resource_list.html",
        resource=config,
        rows=rows,
        columns=[label for label, _ in config.columns],
        pagination=pagination,
        search_term=q,
    )


@bp.route("/<resource_key>/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_resource(resource_key: str):
    config = RESOURCES.get(resource_key)
    if config is None:
        return render_template("errors/404.html"), 404
    form = config.form_class()
    if form.validate_on_submit():
        instance = config.model()
        form.apply(instance)
        save_instance(instance)
        flash(f"{config.singular} created successfully.", "success")
        return redirect(url_for("prep_tasks.detail_resource", resource_key=resource_key, resource_id=instance.id))
    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="create")


@bp.get("/<resource_key>/<int:resource_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def detail_resource(resource_key: str, resource_id: int):
    config = RESOURCES.get(resource_key)
    if config is None:
        return render_template("errors/404.html"), 404
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    details = [{"label": label, "value": _display_value(getter(instance))} for label, getter in config.columns]
    return render_template("dashboard/resource_detail.html", resource=config, instance=instance, details=details)


@bp.route("/<resource_key>/<int:resource_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def edit_resource(resource_key: str, resource_id: int):
    config = RESOURCES.get(resource_key)
    if config is None:
        return render_template("errors/404.html"), 404
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    form = _build_form(config, instance)
    if form.validate_on_submit():
        form.apply(instance)
        save_instance(instance)
        flash(f"{config.singular} updated successfully.", "success")
        return redirect(url_for("prep_tasks.detail_resource", resource_key=resource_key, resource_id=instance.id))
    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="edit")


@bp.post("/<resource_key>/<int:resource_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def archive_resource_view(resource_key: str, resource_id: int):
    config = RESOURCES.get(resource_key)
    if config is None:
        return render_template("errors/404.html"), 404
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    if resource_key == "templates":
        instance.default_enabled = False
        save_instance(instance)
    elif resource_key == "tasks":
        from app.models import PrepTaskStatus

        instance.status = PrepTaskStatus.CANCELED
        save_instance(instance)
    else:
        archive_instance(instance)
    flash(f"{config.singular} archived.", "success")
    return redirect(url_for("prep_tasks.list_resource", resource_key=resource_key))
