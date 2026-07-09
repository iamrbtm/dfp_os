from __future__ import annotations

from decimal import Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from app.blueprints.pos import bp
from app.extensions import db
from app.forms.pos import PosCloseSessionForm, PosSessionForm
from app.models import (
    Category,
    Customer,
    PosSale,
    PosSession,
    PosSessionStatus,
    Product,
    ProductStatus,
    UserRole,
)
from app.services.crud import apply_search, paginate_query
from app.services.audit_client import AuditDispatchError
from app.services.pos import (
    close_session,
    create_sale,
    get_session_summary,
    open_session,
    refund_sale,
    void_session,
)
from app.services.storage import send_storage_reference
from app.utils.auth import roles_required


@bp.route("/")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def index():
    active = PosSession.query.filter_by(status=PosSessionStatus.OPEN).order_by(PosSession.id.desc()).first()
    if active:
        return redirect(url_for("pos.pos_screen", session_id=active.id))
    return redirect(url_for("pos.session_list"))


@bp.route("/sessions")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def session_list():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    q = request.args.get("q", "").strip()

    query = select(PosSession).order_by(PosSession.id.desc())
    if q:
        query = apply_search(query, PosSession, q, ["session_number", "notes"])
    pagination = paginate_query(query, page, per_page)
    sessions = pagination.items

    return render_template(
        "pos/session_list.html",
        sessions=sessions,
        pagination=pagination,
        q=q,
    )


@bp.route("/sessions/new", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def session_new():
    form = PosSessionForm()
    if form.validate_on_submit():
        session = open_session(
            user_id=current_user.id,
            opening_cash=form.opening_cash.data or Decimal("0"),
            market_id=form.market_id.data if form.market_id.data and form.market_id.data > 0 else None,
            inventory_location_id=form.inventory_location_id.data if form.inventory_location_id.data and form.inventory_location_id.data > 0 else None,
            notes=form.notes.data,
        )
        flash(f"POS session {session.session_number} opened.")
        return redirect(url_for("pos.pos_screen", session_id=session.id))
    return render_template("pos/session_form.html", form=form, title="Open POS Session")


@bp.route("/sessions/<int:session_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def session_detail(session_id):
    session = db.session.get(PosSession, session_id)
    if not session:
        flash("Session not found.", "error")
        return redirect(url_for("pos.session_list"))
    summary = get_session_summary(session_id)
    return render_template("pos/session_detail.html", summary=summary, session=session)


@bp.route("/sessions/<int:session_id>/close", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def session_close(session_id):
    session = db.session.get(PosSession, session_id)
    if not session or session.status != PosSessionStatus.OPEN:
        flash("Session is not open.", "error")
        return redirect(url_for("pos.session_list"))

    summary = get_session_summary(session_id)
    expected_cash = summary["expected_cash"]

    form = PosCloseSessionForm()
    if form.validate_on_submit():
        closing_cash = (
            (form.hundreds.data or Decimal("0")) * 100
            + (form.fifties.data or Decimal("0")) * 50
            + (form.twenties.data or Decimal("0")) * 20
            + (form.tens.data or Decimal("0")) * 10
            + (form.fives.data or Decimal("0")) * 5
            + (form.ones.data or Decimal("0")) * 1
            + (form.quarters.data or Decimal("0")) * Decimal("0.25")
            + (form.dimes.data or Decimal("0")) * Decimal("0.10")
            + (form.nickels.data or Decimal("0")) * Decimal("0.05")
            + (form.pennies.data or Decimal("0")) * Decimal("0.01")
        )
        close_session(
            session_id=session_id,
            closed_by_user_id=current_user.id,
            closing_cash=closing_cash,
            notes=form.notes.data,
        )
        flash(f"Session {session.session_number} closed.")
        return redirect(url_for("pos.session_detail", session_id=session_id))
    return render_template(
        "pos/session_close.html",
        form=form,
        session=session,
        expected_cash=expected_cash,
        summary=summary,
    )


@bp.route("/sessions/<int:session_id>/void", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def session_void(session_id):
    void_session(session_id)
    flash("Session voided.")
    return redirect(url_for("pos.session_list"))


@bp.route("/sessions/<int:session_id>/screen")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def pos_screen(session_id):
    session = db.session.get(PosSession, session_id)
    if not session or session.status != PosSessionStatus.OPEN:
        flash("Session is not open.", "error")
        return redirect(url_for("pos.session_list"))

    categories = Category.query.filter_by(is_pos_visible=True).order_by(Category.sort_order).all()
    products = (
        Product.query.filter(
            Product.is_pos_visible,
            Product.status.in_([ProductStatus.ACTIVE, ProductStatus.HIDDEN]),
            Product.deleted_at.is_(None),
        )
        .order_by(Product.name)
        .all()
    )
    customers = Customer.query.filter(Customer.deleted_at.is_(None)).order_by(Customer.first_name, Customer.last_name).all()
    return render_template(
        "pos/index.html",
        session=session,
        categories=categories,
        products=products,
        customers=customers,
    )


@bp.route("/sessions/<int:session_id>/products")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def product_grid(session_id):
    category_id = request.args.get("category", type=int)
    q = request.args.get("q", "").strip()

    query = Product.query.filter(
        Product.is_pos_visible,
        Product.status.in_([ProductStatus.ACTIVE, ProductStatus.HIDDEN]),
        Product.deleted_at.is_(None),
    )
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if q:
        query = query.filter(
            db.or_(
                Product.name.ilike(f"%{q}%"),
                Product.short_description.ilike(f"%{q}%"),
                Product.tags.ilike(f"%{q}%"),
            )
        )
    products = query.order_by(Product.name).all()
    return render_template("pos/_product_grid.html", products=products)


@bp.route("/sessions/<int:session_id>/checkout", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def checkout(session_id):
    session = db.session.get(PosSession, session_id)
    if not session or session.status != PosSessionStatus.OPEN:
        return {"error": "Session is not open"}, 400

    data = request.get_json(force=True)
    if not data or "items" not in data or not data["items"]:
        return {"error": "Cart is empty"}, 400

    try:
        sale, order = create_sale(
            session_id=session_id,
            payment_method=data["payment_method"],
            amount_received=Decimal(str(data.get("amount_received", 0))),
            items=data["items"],
            customer_id=data.get("customer_id"),
            notes=data.get("notes"),
            tax_total=Decimal(str(data.get("tax_total", 0))),
        )
    except ValueError as e:
        return {"error": str(e)}, 400
    except AuditDispatchError:
        return {"error": "Sale could not be completed because audit logging is unavailable."}, 503

    return {"redirect": url_for("pos.receipt", session_id=session_id, sale_id=sale.id)}


@bp.route("/sessions/<int:session_id>/receipt/<int:sale_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def receipt(session_id, sale_id):
    session = db.session.get(PosSession, session_id)
    sale = db.session.get(PosSale, sale_id)
    if not session or not sale or sale.pos_session_id != session_id:
        flash("Sale not found.", "error")
        return redirect(url_for("pos.pos_screen", session_id=session_id))
    return render_template("pos/receipt.html", session=session, sale=sale)


@bp.route("/sessions/<int:session_id>/sales/<int:sale_id>/refund", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def sale_refund(session_id: int, sale_id: int):
    session = db.session.get(PosSession, session_id)
    sale = db.session.get(PosSale, sale_id)
    if not session or not sale or sale.pos_session_id != session_id:
        flash("Sale not found.", "error")
        return redirect(url_for("pos.session_detail", session_id=session_id))
    restock = request.form.get("restock_inventory", "1") == "1"
    notes = request.form.get("notes", "").strip() or None
    try:
        refund_sale(
            sale_id=sale.id,
            actor_id=current_user.id,
            restock=restock,
            notes=notes,
        )
    except ValueError as exc:
        flash(str(exc), "danger")
    else:
        flash("Sale refunded.", "success")
    return redirect(url_for("pos.session_detail", session_id=session_id))


@bp.route("/customers/quick", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def quick_customer():
    data = request.get_json(force=True)
    first = data.get("first_name", "").strip()
    last = data.get("last_name", "").strip()
    if not first or not last:
        return {"error": "First and last name required"}, 400
    c = Customer(first_name=first, last_name=last)
    c.email = data.get("email", "").strip() or None
    c.phone = data.get("phone", "").strip() or None
    db.session.add(c)
    db.session.commit()
    return {"id": c.id, "display_name": f"{c.first_name} {c.last_name}"}


@bp.route("/product-image/<int:product_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def product_image(product_id: int):
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)

    ref = product.pos_image_path or product.default_image_path
    if not ref:
        abort(404)

    return send_storage_reference(ref, mimetype="image/jpeg")
