from __future__ import annotations

from dataclasses import dataclass

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.blueprints.prep_tasks import bp
from app.forms.admin import PrepTaskAdminForm, PrepTaskTemplateForm
from app.models import PrepTask, PrepTaskCategory, PrepTaskStatus, PrepTaskTemplate, UserRole
from app.services.admin_mutations import (
    create_resource as create_admin_resource,
    snapshot_instance,
    update_resource as update_admin_resource,
)
from app.services.crud import apply_search, get_by_id, paginate_query
from app.services.follow_ups import (
    archive_follow_up,
    complete_follow_up,
    get_follow_up_queue,
    reopen_follow_up,
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
        try:
            create_admin_resource(instance, actor_id=current_user.id)
        except IntegrityError:
            from app.extensions import db

            db.session.rollback()
            flash(f"Unable to save that {config.singular.lower()}.", "danger")
            return (
                render_template(
                    "dashboard/resource_form.html", resource=config, form=form, mode="create"
                ),
                400,
            )
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
        before_state = snapshot_instance(instance)
        form.apply(instance)
        try:
            update_admin_resource(instance, before_state=before_state, actor_id=current_user.id)
        except IntegrityError:
            from app.extensions import db

            db.session.rollback()
            flash(f"Unable to update that {config.singular.lower()}.", "danger")
            return (
                render_template(
                    "dashboard/resource_form.html", resource=config, form=form, mode="edit"
                ),
                400,
            )
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
    before_state = snapshot_instance(instance)
    if resource_key == "templates":
        instance.default_enabled = False
    elif resource_key == "tasks":
        instance.status = PrepTaskStatus.CANCELED
    update_admin_resource(instance, before_state=before_state, actor_id=current_user.id)
    flash(f"{config.singular} archived.", "success")
    return redirect(url_for("prep_tasks.list_resource", resource_key=resource_key))


@bp.get("/follow_ups/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def follow_up_queue():
    market_id = request.args.get("market_id", type=int)
    q = request.args.get("q", "").strip()
    tasks = get_follow_up_queue(market_id=market_id)
    if q:
        tasks = [t for t in tasks if q.lower() in (t.title or "").lower() or (t.follow_up_type or "").lower() == q.lower()]
    page = request.args.get("page", 1, type=int)
    per_page = 25
    total = len(tasks)
    start = (page - 1) * per_page
    paged_tasks = tasks[start:start + per_page]
    from math import ceil
    total_pages = max(1, ceil(total / per_page))
    from dataclasses import dataclass

    @dataclass
    class Pager:
        page: int
        per_page: int
        total: int
        pages: int
        items: list
        has_prev: bool
        has_next: bool
        prev_num: int
        next_num: int

    pagination = Pager(
        page=page, per_page=per_page, total=total, pages=total_pages,
        items=paged_tasks,
        has_prev=page > 1, has_next=page < total_pages,
        prev_num=page - 1, next_num=page + 1,
    )
    from datetime import datetime, timezone
    from app.models import Market
    markets = Market.query.order_by(Market.event_date.desc(), Market.name).all()
    return render_template(
        "dashboard/prep_tasks/follow_up_queue.html",
        tasks=paged_tasks,
        pagination=pagination,
        search_term=q,
        current_market_id=market_id,
        markets=markets,
        now=datetime.now(timezone.utc),
    )


@bp.post("/follow_ups/<int:task_id>/complete")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def follow_up_complete(task_id: int):
    task = get_by_id(PrepTask, task_id)
    if task is None:
        return render_template("errors/404.html"), 404
    complete_follow_up(task, actor=current_user)
    flash("Follow-up marked complete.", "success")
    return redirect(request.referrer or url_for("prep_tasks.follow_up_queue"))


@bp.post("/follow_ups/<int:task_id>/reopen")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def follow_up_reopen(task_id: int):
    task = get_by_id(PrepTask, task_id)
    if task is None:
        return render_template("errors/404.html"), 404
    reopen_follow_up(task, actor=current_user)
    flash("Follow-up reopened.", "success")
    return redirect(request.referrer or url_for("prep_tasks.follow_up_queue"))


@bp.post("/follow_ups/<int:task_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def follow_up_archive(task_id: int):
    task = get_by_id(PrepTask, task_id)
    if task is None:
        return render_template("errors/404.html"), 404
    archive_follow_up(task, actor=current_user)
    flash("Follow-up archived.", "success")
    return redirect(request.referrer or url_for("prep_tasks.follow_up_queue"))
