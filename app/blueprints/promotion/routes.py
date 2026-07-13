from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from app.blueprints.promotion import bp
from app.extensions import db
from app.forms.promotion import ContentDraftForm, SignAssetForm
from app.models import UserRole
from app.models.promotion import (
    ContentChannel,
    ContentDraft,
    ContentStatus,
    SignAsset,
    SignStatus,
)
from app.services.admin_mutations import create_resource, snapshot_instance, update_resource
from app.services.crud import apply_search, get_by_id, paginate_query
from app.services.promotion import (
    approve_draft,
    approve_sign,
    archive_draft,
    archive_sign,
    generate_draft_from_custom_request,
    generate_draft_from_market,
    generate_draft_from_product,
    publish_draft,
    save_sign_html,
)
from app.utils.auth import roles_required

DRAFT_SEARCH_FIELDS = ["title", "caption", "notes", "media_reference"]
SIGN_SEARCH_FIELDS = ["title", "subtitle", "short_description", "care_note"]


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


def _draft_columns(draft: ContentDraft) -> list[str]:
    return [
        draft.title,
        _display_value(draft.channel),
        _display_value(draft.status),
        draft.product.name if draft.product else None,
        _display_value(draft.planned_publish_date),
    ]


def _sign_columns(sign: SignAsset) -> list[str]:
    return [
        sign.title,
        _display_value(sign.status),
        sign.product.name if sign.product else None,
        sign.price_display or "\u2014",
        "Yes" if sign.is_active else "No",
    ]


@bp.get("/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def root():
    return redirect(url_for("promotion.draft_list"))


@bp.get("/drafts/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_list():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    channel_filter = request.args.get("channel", "").strip()

    stmt = select(ContentDraft).order_by(ContentDraft.updated_at.desc())
    if q:
        stmt = apply_search(stmt, ContentDraft, q, DRAFT_SEARCH_FIELDS)
    if status_filter:
        stmt = stmt.where(ContentDraft.status == status_filter)
    if channel_filter:
        stmt = stmt.where(ContentDraft.channel == channel_filter)

    pagination = paginate_query(stmt, page, 25)
    rows = [
        {"id": d.id, "cells": _draft_columns(d)}
        for d in pagination.items
    ]

    return render_template(
        "dashboard/promotion/draft_list.html",
        drafts=pagination.items,
        rows=rows,
        columns=["Title", "Channel", "Status", "Product", "Publish Date"],
        pagination=pagination,
        search_term=q,
        status_filter=status_filter,
        channel_filter=channel_filter,
        status_choices=list(ContentStatus),
        channel_choices=list(ContentChannel),
    )


@bp.route("/drafts/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_create():
    form = ContentDraftForm()
    if form.validate_on_submit():
        draft = ContentDraft(created_by_user_id=current_user.id)
        form.apply(draft)
        create_resource(draft, actor_id=current_user.id)
        flash("Content draft created.", "success")
        return redirect(url_for("promotion.draft_detail", draft_id=draft.id))
    return render_template(
        "dashboard/promotion/draft_form.html", form=form, mode="create"
    )


@bp.route("/drafts/<int:draft_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_edit(draft_id: int):
    draft = get_by_id(ContentDraft, draft_id)
    if draft is None:
        return render_template("errors/404.html"), 404
    form = ContentDraftForm(obj=draft)
    if form.validate_on_submit():
        before_state = snapshot_instance(draft)
        form.apply(draft)
        update_resource(draft, before_state=before_state, actor_id=current_user.id)
        flash("Content draft updated.", "success")
        return redirect(url_for("promotion.draft_detail", draft_id=draft.id))
    return render_template(
        "dashboard/promotion/draft_form.html", form=form, mode="edit", draft=draft
    )


@bp.get("/drafts/<int:draft_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_detail(draft_id: int):
    draft = get_by_id(ContentDraft, draft_id)
    if draft is None:
        return render_template("errors/404.html"), 404
    return render_template(
        "dashboard/promotion/draft_detail.html",
        draft=draft,
    )


@bp.post("/drafts/<int:draft_id>/approve")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_approve(draft_id: int):
    draft = get_by_id(ContentDraft, draft_id)
    if draft is None:
        return render_template("errors/404.html"), 404
    if draft.status == ContentStatus.DRAFT:
        draft.status = ContentStatus.NEEDS_REVIEW
        db.session.commit()
    approve_draft(draft, actor=current_user)
    flash("Draft approved.", "success")
    return redirect(request.referrer or url_for("promotion.draft_detail", draft_id=draft.id))


@bp.post("/drafts/<int:draft_id>/publish")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_publish(draft_id: int):
    draft = get_by_id(ContentDraft, draft_id)
    if draft is None:
        return render_template("errors/404.html"), 404
    publish_draft(draft, actor=current_user)
    flash("Draft marked as published.", "success")
    return redirect(request.referrer or url_for("promotion.draft_detail", draft_id=draft.id))


@bp.post("/drafts/<int:draft_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_archive(draft_id: int):
    draft = get_by_id(ContentDraft, draft_id)
    if draft is None:
        return render_template("errors/404.html"), 404
    archive_draft(draft, actor=current_user)
    flash("Draft archived.", "success")
    return redirect(request.referrer or url_for("promotion.draft_list"))


@bp.post("/drafts/generate-from-product/<int:product_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_generate_from_product(product_id: int):
    draft = generate_draft_from_product(product_id, actor_id=current_user.id)
    if draft is None:
        flash("Product not found.", "danger")
        return redirect(request.referrer or url_for("promotion.draft_list"))
    flash(f"Draft generated from product.", "success")
    return redirect(url_for("promotion.draft_edit", draft_id=draft.id))


@bp.post("/drafts/generate-from-market/<int:market_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_generate_from_market(market_id: int):
    draft = generate_draft_from_market(market_id, actor_id=current_user.id)
    if draft is None:
        flash("Market not found.", "danger")
        return redirect(request.referrer or url_for("promotion.draft_list"))
    flash(f"Draft generated from market.", "success")
    return redirect(url_for("promotion.draft_edit", draft_id=draft.id))


@bp.post("/drafts/generate-from-custom-request/<int:cr_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def draft_generate_from_custom_request(cr_id: int):
    draft = generate_draft_from_custom_request(cr_id, actor_id=current_user.id)
    if draft is None:
        flash("Custom request not found.", "danger")
        return redirect(request.referrer or url_for("promotion.draft_list"))
    flash(f"Draft generated from custom request.", "success")
    return redirect(url_for("promotion.draft_edit", draft_id=draft.id))


@bp.get("/signs/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sign_list():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()

    stmt = select(SignAsset).order_by(SignAsset.updated_at.desc())
    if q:
        stmt = apply_search(stmt, SignAsset, q, SIGN_SEARCH_FIELDS)
    if status_filter:
        stmt = stmt.where(SignAsset.status == status_filter)

    pagination = paginate_query(stmt, page, 25)
    rows = [
        {"id": s.id, "cells": _sign_columns(s)}
        for s in pagination.items
    ]

    return render_template(
        "dashboard/promotion/sign_list.html",
        signs=pagination.items,
        rows=rows,
        columns=["Title", "Status", "Product", "Price", "Active"],
        pagination=pagination,
        search_term=q,
        status_filter=status_filter,
        status_choices=list(SignStatus),
    )


@bp.route("/signs/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sign_create():
    form = SignAssetForm()
    if form.validate_on_submit():
        sign = SignAsset()
        form.apply(sign)
        create_resource(sign, actor_id=current_user.id)
        save_sign_html(sign)
        flash("Sign created.", "success")
        return redirect(url_for("promotion.sign_detail", sign_id=sign.id))
    return render_template(
        "dashboard/promotion/sign_form.html", form=form, mode="create"
    )


@bp.route("/signs/<int:sign_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sign_edit(sign_id: int):
    sign = get_by_id(SignAsset, sign_id)
    if sign is None:
        return render_template("errors/404.html"), 404
    form = SignAssetForm(obj=sign)
    if form.validate_on_submit():
        before_state = snapshot_instance(sign)
        form.apply(sign)
        update_resource(sign, before_state=before_state, actor_id=current_user.id)
        save_sign_html(sign)
        flash("Sign updated.", "success")
        return redirect(url_for("promotion.sign_detail", sign_id=sign.id))
    return render_template(
        "dashboard/promotion/sign_form.html", form=form, mode="edit", sign=sign
    )


@bp.get("/signs/<int:sign_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sign_detail(sign_id: int):
    sign = get_by_id(SignAsset, sign_id)
    if sign is None:
        return render_template("errors/404.html"), 404
    return render_template(
        "dashboard/promotion/sign_detail.html",
        sign=sign,
    )


@bp.get("/signs/<int:sign_id>/print")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sign_print(sign_id: int):
    sign = get_by_id(SignAsset, sign_id)
    if sign is None:
        return render_template("errors/404.html"), 404
    return render_template(
        "dashboard/promotion/sign_print.html",
        sign=sign,
    )


@bp.post("/signs/<int:sign_id>/approve")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sign_approve(sign_id: int):
    sign = get_by_id(SignAsset, sign_id)
    if sign is None:
        return render_template("errors/404.html"), 404
    approve_sign(sign, actor=current_user)
    flash("Sign approved.", "success")
    return redirect(request.referrer or url_for("promotion.sign_detail", sign_id=sign.id))


@bp.post("/signs/<int:sign_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sign_archive(sign_id: int):
    sign = get_by_id(SignAsset, sign_id)
    if sign is None:
        return render_template("errors/404.html"), 404
    archive_sign(sign, actor=current_user)
    flash("Sign archived.", "success")
    return redirect(request.referrer or url_for("promotion.sign_list"))


@bp.post("/signs/<int:sign_id>/regenerate-html")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sign_regenerate(sign_id: int):
    sign = get_by_id(SignAsset, sign_id)
    if sign is None:
        return render_template("errors/404.html"), 404
    save_sign_html(sign)
    flash("Sign HTML regenerated.", "success")
    return redirect(url_for("promotion.sign_detail", sign_id=sign.id))
