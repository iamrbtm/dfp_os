from __future__ import annotations

from dataclasses import dataclass

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.blueprints.print_jobs import bp
from app.forms import PrintFailureAutopsyForm, PrintJobForm
from app.models import PrintFailureAutopsy, PrintJob, UserRole
from app.services.crud import (
    apply_search,
    get_by_id,
    paginate_query,
)
from app.services.admin_mutations import snapshot_instance
from app.services.print_jobs import archive_print_job, create_print_job, update_print_job
from app.services.printer_reliability import (
    create_autopsy_for_failed_job,
    needs_failure_autopsy,
    resolve_autopsy,
    update_autopsy,
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


PRINT_JOB_RESOURCES: dict[str, ResourceConfig] = {
    "print-jobs": ResourceConfig(
        key="print-jobs",
        singular="Print Job",
        plural="Print Jobs",
        model=PrintJob,
        form_class=PrintJobForm,
        search_fields=["label", "notes"],
        columns=[
            ("Label", lambda item: item.label or "\u2014"),
            ("Status", lambda item: item.status),
            ("Printer", lambda item: item.printer.name if item.printer else "\u2014"),
            ("Assigned To", lambda item: item.assigned_to.full_name if item.assigned_to else "\u2014"),
            ("Priority", lambda item: item.priority),
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
def print_jobs_root():
    return redirect(url_for("print_jobs.list_resource", resource_key="print-jobs"))


@bp.route("/<resource_key>/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_resource(resource_key: str):
    if resource_key not in PRINT_JOB_RESOURCES:
        return render_template("errors/404.html"), 404
    config = PRINT_JOB_RESOURCES[resource_key]
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
def create_resource(resource_key: str = "print-jobs"):
    if resource_key not in PRINT_JOB_RESOURCES:
        return render_template("errors/404.html"), 404
    config = PRINT_JOB_RESOURCES[resource_key]
    form = config.form_class()
    if form.validate_on_submit():
        instance = config.model()
        form.apply(instance)
        try:
            create_print_job(instance, actor_id=current_user.id)
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
        return redirect(
            url_for(
                "print_jobs.detail_resource",
                resource_key=resource_key,
                resource_id=instance.id,
            )
        )
    return render_template(
        "dashboard/resource_form.html", resource=config, form=form, mode="create"
    )


@bp.get("/<int:resource_id>")
@bp.get("/<resource_key>/<int:resource_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def detail_resource(resource_id: int, resource_key: str = "print-jobs"):
    if resource_key not in PRINT_JOB_RESOURCES:
        return render_template("errors/404.html"), 404
    config = PRINT_JOB_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    details = [
        {"label": label, "value": _display_value(getter(instance))}
        for label, getter in config.columns
    ]
    return render_template(
        "print_jobs/detail.html",
        resource=config,
        instance=instance,
        details=details,
        needs_autopsy=needs_failure_autopsy(instance),
    )


@bp.route("/<int:resource_id>/edit", methods=["GET", "POST"])
@bp.route("/<resource_key>/<int:resource_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def edit_resource(resource_id: int, resource_key: str = "print-jobs"):
    if resource_key not in PRINT_JOB_RESOURCES:
        return render_template("errors/404.html"), 404
    config = PRINT_JOB_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    form = _build_form(config, instance)
    if form.validate_on_submit():
        before_state = snapshot_instance(instance)
        form.apply(instance)
        try:
            update_print_job(instance, before_state=before_state, actor_id=current_user.id)
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
        return redirect(
            url_for(
                "print_jobs.detail_resource",
                resource_key=resource_key,
                resource_id=instance.id,
            )
        )
    return render_template("dashboard/resource_form.html", resource=config, form=form, mode="edit")


@bp.post("/<int:resource_id>/archive")
@bp.post("/<resource_key>/<int:resource_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def archive_resource_view(resource_id: int, resource_key: str = "print-jobs"):
    if resource_key not in PRINT_JOB_RESOURCES:
        return render_template("errors/404.html"), 404
    config = PRINT_JOB_RESOURCES[resource_key]
    instance = get_by_id(config.model, resource_id)
    if instance is None:
        return render_template("errors/404.html"), 404
    archive_print_job(instance, actor_id=current_user.id)
    flash(f"{config.singular} archived.", "success")
    return redirect(url_for("print_jobs.list_resource", resource_key=resource_key))


@bp.route("/<int:print_job_id>/autopsy", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_autopsy(print_job_id: int):
    print_job = get_by_id(PrintJob, print_job_id)
    if print_job is None:
        return render_template("errors/404.html"), 404
    form = PrintFailureAutopsyForm()
    if form.validate_on_submit():
        autopsy = PrintFailureAutopsy()
        form.apply(autopsy)
        create_autopsy_for_failed_job(print_job, autopsy, actor_id=current_user.id)
        flash("Failure autopsy saved.", "success")
        return redirect(url_for("print_jobs.detail_resource", resource_id=print_job.id))
    return render_template("print_jobs/autopsy_form.html", print_job=print_job, form=form, mode="create")


@bp.route("/autopsies/<int:autopsy_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def edit_autopsy(autopsy_id: int):
    autopsy = get_by_id(PrintFailureAutopsy, autopsy_id)
    if autopsy is None:
        return render_template("errors/404.html"), 404
    form = _build_autopsy_form(autopsy)
    if form.validate_on_submit():
        before_state = snapshot_instance(autopsy)
        form.apply(autopsy)
        update_autopsy(autopsy, before_state=before_state, actor_id=current_user.id)
        flash("Failure autopsy updated.", "success")
        return redirect(url_for("print_jobs.detail_resource", resource_id=autopsy.print_job_id))
    return render_template("print_jobs/autopsy_form.html", print_job=autopsy.print_job, form=form, mode="edit", autopsy=autopsy)


@bp.post("/autopsies/<int:autopsy_id>/resolve")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def resolve_autopsy_view(autopsy_id: int):
    autopsy = get_by_id(PrintFailureAutopsy, autopsy_id)
    if autopsy is None:
        return render_template("errors/404.html"), 404
    resolve_autopsy(
        autopsy,
        resolution_notes=request.form.get("resolution_notes", "").strip() or None,
        actor_id=current_user.id,
    )
    flash("Failure autopsy resolved.", "success")
    return redirect(url_for("print_jobs.detail_resource", resource_id=autopsy.print_job_id))


def _build_autopsy_form(autopsy: PrintFailureAutopsy):
    data = {}
    for field_name in PrintFailureAutopsyForm()._fields:
        if field_name in {"csrf_token", "submit"}:
            continue
        value = getattr(autopsy, field_name, None)
        if hasattr(value, "value"):
            value = value.value
        data[field_name] = value
    return PrintFailureAutopsyForm(data=data)
