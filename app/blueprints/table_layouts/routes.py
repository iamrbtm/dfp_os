from __future__ import annotations

from pathlib import Path

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from werkzeug.utils import secure_filename

from app.blueprints.table_layouts import bp
from app.extensions import db
from app.forms.table_layout import (
    MarketTableLayoutForm,
    MarketTablePlacementForm,
)
from app.models import (
    Market,
    MarketTableLayout,
    MarketTablePlacement,
    MarketTableSection,
    Product,
    TableSectionType,
    UserRole,
)
from app.services.audit import record_audit_event
from app.services.crud import get_by_id, paginate_query
from app.utils.auth import roles_required

def _audit(action, entity_type, entity_id, *, actor=None, before_state=None, after_state=None, metadata=None):
    record_audit_event(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=str(actor.id) if actor else None,
        actor_type="user" if actor else "system",
        actor_display_name=getattr(actor, "full_name", None) or getattr(actor, "email", None),
        source_module=__name__,
        before_state=before_state,
        after_state=after_state,
        metadata=metadata,
    )


DEFAULT_SECTIONS = [
    (TableSectionType.FRONT_LEFT, "Front Left", 1),
    (TableSectionType.FRONT_CENTER, "Front Center", 2),
    (TableSectionType.FRONT_RIGHT, "Front Right", 3),
    (TableSectionType.BACK_LEFT, "Back Left", 4),
    (TableSectionType.BACK_CENTER, "Back Center", 5),
    (TableSectionType.BACK_RIGHT, "Back Right", 6),
    (TableSectionType.IMPULSE_TRAY, "Impulse Tray", 7),
]


@bp.get("/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def list_layouts():
    market_id = request.args.get("market_id", type=int)
    page = request.args.get("page", 1, type=int)
    query = select(MarketTableLayout).order_by(MarketTableLayout.created_at.desc())
    if market_id:
        query = query.where(MarketTableLayout.market_id == market_id)
    pagination = paginate_query(query, page, 20)
    templates = MarketTableLayout.query.filter_by(is_template=True).order_by(MarketTableLayout.name).all()
    return render_template(
        "dashboard/table_layouts/list.html",
        layouts=pagination.items,
        pagination=pagination,
        current_market_id=market_id,
        templates=templates,
    )


@bp.route("/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_layout():
    form = MarketTableLayoutForm()
    market_id = request.args.get("market_id", type=int)
    copy_from = request.args.get("copy_from", type=int)
    market = get_by_id(Market, market_id) if market_id else None

    if form.validate_on_submit():
        if not form.is_template.data and not market_id:
            flash("Select a market for this layout, or save it as a template.", "danger")
            return render_template(
                "dashboard/table_layouts/form.html",
                form=form,
                mode="create",
                market=market,
            )

        layout = MarketTableLayout(market_id=market_id)
        layout.name = form.name.data.strip()
        layout.notes = form.notes.data
        layout.is_template = form.is_template.data

        if form.photo.data:
            photo = _save_photo(form.photo.data, layout)
            if photo:
                layout.photo_path = photo

        if copy_from:
            source = get_by_id(MarketTableLayout, copy_from)
            if source:
                layout.copied_from_layout_id = source.id

        db.session.add(layout)
        db.session.commit()

        if copy_from and source:
            _copy_sections(source, layout)

        if not copy_from:
            for sec_type, label, sort in DEFAULT_SECTIONS:
                db.session.add(MarketTableSection(
                    layout_id=layout.id,
                    section_type=sec_type,
                    label=label,
                    sort_order=sort,
                ))
            db.session.commit()

        _audit("table_layout.created", "market_table_layout", layout.id, actor=current_user)
        flash("Table layout created.", "success")
        return redirect(url_for("table_layouts.detail_layout", layout_id=layout.id))

    return render_template(
        "dashboard/table_layouts/form.html",
        form=form,
        mode="create",
        market=market,
    )


@bp.get("/<int:layout_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def detail_layout(layout_id: int):
    layout = get_by_id(MarketTableLayout, layout_id)
    if layout is None:
        return render_template("errors/404.html"), 404
    sections = MarketTableSection.query.filter_by(layout_id=layout.id).order_by(
        MarketTableSection.sort_order
    ).all()
    placement_form = MarketTablePlacementForm()
    markets = Market.query.order_by(Market.event_date.desc()).all()
    return render_template(
        "dashboard/table_layouts/detail.html",
        layout=layout,
        sections=sections,
        placement_form=placement_form,
        markets=markets,
    )


@bp.route("/<int:layout_id>/edit", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def edit_layout(layout_id: int):
    layout = get_by_id(MarketTableLayout, layout_id)
    if layout is None:
        return render_template("errors/404.html"), 404
    form = MarketTableLayoutForm(obj=layout)
    if form.validate_on_submit():
        layout.name = form.name.data.strip()
        layout.notes = form.notes.data
        layout.is_template = form.is_template.data

        if form.photo.data:
            photo = _save_photo(form.photo.data, layout)
            if photo:
                layout.photo_path = photo

        db.session.commit()
        _audit("table_layout.updated", "market_table_layout", layout.id, actor=current_user)
        flash("Layout updated.", "success")
        return redirect(url_for("table_layouts.detail_layout", layout_id=layout.id))
    return render_template(
        "dashboard/table_layouts/form.html",
        form=form,
        mode="edit",
        layout=layout,
    )


@bp.route("/<int:layout_id>/sections/new", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def add_section(layout_id: int):
    layout = get_by_id(MarketTableLayout, layout_id)
    if layout is None:
        return render_template("errors/404.html"), 404
    section_type = request.form.get("section_type", "")
    label = request.form.get("label", "").strip()
    if not label or not section_type:
        flash("Section type and label are required.", "danger")
        return redirect(url_for("table_layouts.detail_layout", layout_id=layout.id))
    max_sort = db.session.query(db.func.max(MarketTableSection.sort_order)).filter(
        MarketTableSection.layout_id == layout.id
    ).scalar() or 0
    section = MarketTableSection(
        layout_id=layout.id,
        section_type=TableSectionType(section_type),
        label=label,
        sort_order=max_sort + 1,
    )
    db.session.add(section)
    db.session.commit()
    _audit("table_layout.section_added", "market_table_section", section.id, actor=current_user)
    flash("Section added.", "success")
    return redirect(url_for("table_layouts.detail_layout", layout_id=layout.id))


@bp.post("/<int:layout_id>/sections/<int:section_id>/delete")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def delete_section(layout_id: int, section_id: int):
    section = get_by_id(MarketTableSection, section_id)
    if section is None or section.layout_id != layout_id:
        return render_template("errors/404.html"), 404
    _audit("table_layout.section_deleted", "market_table_section", section.id, actor=current_user, before_state={"label": section.label})
    db.session.delete(section)
    db.session.commit()
    flash("Section deleted.", "success")
    return redirect(url_for("table_layouts.detail_layout", layout_id=layout.id))


@bp.route("/<int:layout_id>/placements/new", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def add_placement(layout_id: int):
    layout = get_by_id(MarketTableLayout, layout_id)
    if layout is None:
        return render_template("errors/404.html"), 404
    form = MarketTablePlacementForm()
    if form.validate_on_submit():
        section_id = request.args.get("section_id", type=int) or form.section_id.data
        if not section_id:
            section_id = request.form.get("section_id", type=int)
        if not section_id:
            flash("Select a section first.", "danger")
            return redirect(url_for("table_layouts.detail_layout", layout_id=layout.id))
        section = get_by_id(MarketTableSection, section_id)
        if section is None or section.layout_id != layout.id:
            return render_template("errors/404.html"), 404
        max_sort = db.session.query(db.func.max(MarketTablePlacement.sort_order)).filter(
            MarketTablePlacement.section_id == section.id
        ).scalar() or 0
        placement = MarketTablePlacement(
            section_id=section.id,
            product_id=form.product_id.data,
            quantity=form.quantity.data,
            sort_order=max_sort + 1,
            notes=form.notes.data,
        )
        db.session.add(placement)
        db.session.commit()
        _audit("table_layout.placement_added", "market_table_placement", placement.id, actor=current_user)
        flash(f"Added {form.quantity.data} x {placement.product.name} to {section.label}.", "success")
    return redirect(url_for("table_layouts.detail_layout", layout_id=layout.id))


@bp.post("/<int:layout_id>/placements/<int:placement_id>/delete")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def delete_placement(layout_id: int, placement_id: int):
    placement = get_by_id(MarketTablePlacement, placement_id)
    if placement is None or placement.section.layout_id != layout_id:
        return render_template("errors/404.html"), 404
    _audit("table_layout.placement_deleted", "market_table_placement", placement.id, actor=current_user, before_state={"product": placement.product.name if placement.product else None})
    db.session.delete(placement)
    db.session.commit()
    flash("Placement removed.", "success")
    return redirect(url_for("table_layouts.detail_layout", layout_id=layout.id))


@bp.post("/<int:layout_id>/apply-to-market")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def apply_template_to_market(layout_id: int):
    template = get_by_id(MarketTableLayout, layout_id)
    if template is None or not template.is_template:
        return render_template("errors/404.html"), 404
    market_id = request.form.get("market_id", type=int)
    market = get_by_id(Market, market_id) if market_id else None
    if not market:
        flash("Select a market to apply this template to.", "danger")
        return redirect(url_for("table_layouts.detail_layout", layout_id=layout_id))
    name = request.form.get("name", "").strip() or f"{template.name} — {market.name}"
    layout = MarketTableLayout(market_id=market.id, name=name, notes=template.notes, is_template=False)
    db.session.add(layout)
    db.session.flush()
    _copy_sections(template, layout)
    _audit("table_layout.created_from_template", "market_table_layout", layout.id, actor=current_user,
           before_state=None, after_state={"template_id": str(template.id), "market_id": str(market.id)})
    flash(f"Template applied to {market.name}.", "success")
    return redirect(url_for("table_layouts.detail_layout", layout_id=layout.id))

@bp.post("/<int:layout_id>/archive")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def archive_layout(layout_id: int):
    layout = get_by_id(MarketTableLayout, layout_id)
    if layout is None:
        return render_template("errors/404.html"), 404
    _audit("table_layout.archived", "market_table_layout", layout.id, actor=current_user)
    db.session.delete(layout)
    db.session.commit()
    flash("Layout archived.", "success")
    return redirect(url_for("table_layouts.list_layouts"))


def _save_photo(file, layout) -> str | None:
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    upload_dir = Path(current_app.config.get("UPLOAD_FOLDER", "uploads")) / "table_layouts"
    upload_dir.mkdir(parents=True, exist_ok=True)
    import uuid
    stored = f"{uuid.uuid4().hex}_{filename}"
    path = upload_dir / stored
    file.save(path)
    return str(path)


def _copy_sections(source: MarketTableLayout, target: MarketTableLayout):
    for src_section in source.sections:
        section = MarketTableSection(
            layout_id=target.id,
            section_type=src_section.section_type,
            label=src_section.label,
            sort_order=src_section.sort_order,
        )
        db.session.add(section)
        db.session.flush()
        for src_placement in src_section.placements:
            db.session.add(MarketTablePlacement(
                section_id=section.id,
                product_id=src_placement.product_id,
                quantity=src_placement.quantity,
                sort_order=src_placement.sort_order,
                notes=src_placement.notes,
            ))
    db.session.commit()
