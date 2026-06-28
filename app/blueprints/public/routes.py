from __future__ import annotations

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from app.blueprints.public import bp
from app.extensions import db
from app.forms import AddToCartForm, CheckoutForm, PublicCustomRequestForm
from app.models import Category, Collection, CustomRequest, Market, MarketStatus, Order, OrderSource, Product, ProductStatus
from app.services.custom_requests import create_custom_request
from app.services.square_checkout import SquareCheckoutError, create_payment_link
from app.services.storefront import (
    StorefrontError,
    add_to_cart,
    available_stock_label,
    build_cart_summary,
    clear_cart,
    create_online_order,
    is_product_purchasable,
    remove_cart_line,
    square_checkout_available,
    update_cart_line,
)


def _public_product_query():
    return select(Product).where(
        Product.is_public.is_(True),
        Product.deleted_at.is_(None),
        Product.status == ProductStatus.ACTIVE,
    )


def _cart_shipping_choice() -> str:
    return request.values.get("fulfillment_method", "pickup").strip() or "pickup"


@bp.get("/")
def home():
    featured = (
        db.session.scalars(_public_product_query().where(Product.is_featured.is_(True)).order_by(Product.name).limit(6))
        .all()
    )
    upcoming = (
        Market.query.filter(Market.status.in_([MarketStatus.ACCEPTED, MarketStatus.SCHEDULED]))
        .order_by(Market.event_date.asc())
        .limit(3)
        .all()
    )
    latest = db.session.scalars(_public_product_query().order_by(Product.created_at.desc()).limit(4)).all()
    return render_template(
        "public/home.html",
        featured=featured,
        latest_products=latest,
        upcoming_markets=upcoming,
    )


@bp.get("/about")
def about():
    return render_template("public/about.html")


@bp.get("/faq")
def faq():
    return render_template("public/faq.html")


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = PublicCustomRequestForm()
    if form.validate_on_submit():
        custom_req = CustomRequest(
            name=form.name.data.strip(),
            email=form.email.data.strip(),
            phone=form.phone.data.strip() if form.phone.data else None,
            description=form.description.data,
            estimated_budget=form.estimated_budget.data.strip() if form.estimated_budget.data else None,
            source="website",
        )
        create_custom_request(custom_req, actor_type="anonymous")
        flash("Thanks for reaching out! We'll get back to you soon.", "success")
        return render_template("public/contact.html", form=PublicCustomRequestForm(), submitted=True)
    return render_template("public/contact.html", form=form, submitted=False)


@bp.get("/shop")
def shop():
    category_slug = request.args.get("category", "").strip()
    collection_slug = request.args.get("collection", "").strip()
    search_term = request.args.get("q", "").strip()

    statement = _public_product_query()
    if category_slug:
        statement = statement.join(Category).where(Category.slug == category_slug)
    if collection_slug:
        statement = statement.join(Collection).where(Collection.slug == collection_slug)
    if search_term:
        statement = statement.where(Product.name.ilike(f"%{search_term}%"))

    products = db.session.scalars(statement.order_by(Product.name.asc())).all()
    categories = (
        Category.query.filter_by(is_public=True).order_by(Category.sort_order, Category.name).all()
    )
    collections = (
        Collection.query.filter_by(is_public=True)
        .order_by(Collection.sort_order, Collection.name)
        .all()
    )
    return render_template(
        "public/shop.html",
        products=products,
        categories=categories,
        collections=collections,
        selected_category=category_slug,
        selected_collection=collection_slug,
        search_term=search_term,
        available_stock_label=available_stock_label,
    )


@bp.route("/shop/<slug>", methods=["GET", "POST"])
def product_detail(slug: str):
    product = Product.query.filter_by(slug=slug, is_public=True).first()
    if product is None or not is_product_purchasable(product):
        abort(404)

    form = AddToCartForm()
    form.product_id.data = str(product.id)

    if form.validate_on_submit():
        try:
            add_to_cart(product, form.quantity.data or 1)
        except StorefrontError as exc:
            flash(str(exc), "danger")
        else:
            flash(f"{product.name} added to your cart.", "success")
            return redirect(url_for("public.cart"))

    return render_template(
        "public/product_detail.html",
        product=product,
        form=form,
        stock_label=available_stock_label(product),
        available_stock_label=available_stock_label,
    )


@bp.get("/cart")
def cart():
    summary = build_cart_summary(current_app.config, fulfillment_method=_cart_shipping_choice())
    return render_template(
        "public/cart.html",
        summary=summary,
        fulfillment_method=_cart_shipping_choice(),
        square_enabled=square_checkout_available(current_app.config),
        venmo_handle=current_app.config.get("SHOP_VENMO_HANDLE"),
    )


@bp.post("/cart/<line_key>/update")
def cart_update(line_key: str):
    quantity = request.form.get("quantity", type=int, default=1)
    try:
        update_cart_line(line_key, quantity)
    except StorefrontError as exc:
        flash(str(exc), "danger")
    else:
        flash("Your cart has been updated.", "success")
    return redirect(url_for("public.cart"))


@bp.post("/cart/<line_key>/remove")
def cart_remove(line_key: str):
    remove_cart_line(line_key)
    flash("Item removed from your cart.", "success")
    return redirect(url_for("public.cart"))


@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    form = CheckoutForm()
    square_enabled = square_checkout_available(current_app.config)
    if not square_enabled:
        form.payment_option.choices = [("venmo", "Reserve now, pay by Venmo")]
        form.payment_option.data = "venmo"

    summary = build_cart_summary(current_app.config, fulfillment_method=form.fulfillment_method.data or "pickup")
    if not summary.lines:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("public.shop"))

    if form.validate_on_submit():
        shipping = {
            "shipping_name": form.shipping_name.data.strip() if form.shipping_name.data else None,
            "shipping_address_line_1": form.shipping_address_line_1.data.strip() if form.shipping_address_line_1.data else None,
            "shipping_address_line_2": form.shipping_address_line_2.data.strip() if form.shipping_address_line_2.data else None,
            "shipping_city": form.shipping_city.data.strip() if form.shipping_city.data else None,
            "shipping_state": form.shipping_state.data.strip() if form.shipping_state.data else None,
            "shipping_postal_code": form.shipping_postal_code.data.strip() if form.shipping_postal_code.data else None,
        }
        try:
            order = create_online_order(
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                phone=form.phone.data,
                notes=form.notes.data,
                fulfillment_method=form.fulfillment_method.data,
                payment_option=form.payment_option.data,
                shipping=shipping,
                config=current_app.config,
            )
        except StorefrontError as exc:
            flash(str(exc), "danger")
        else:
            if form.payment_option.data == "square":
                try:
                    payment_link = create_payment_link(order, current_app.config)
                except SquareCheckoutError as exc:
                    order.payment_provider = "venmo"
                    order.external_payment_reference = current_app.config.get("SHOP_VENMO_HANDLE")
                    db.session.commit()
                    flash(
                        f"Square checkout is unavailable right now, so we saved your order with the Venmo fallback instead. {exc}",
                        "warning",
                    )
                else:
                    order.external_checkout_id = payment_link.payment_link_id
                    order.external_checkout_url = payment_link.url
                    db.session.commit()
                    clear_cart()
                    return redirect(payment_link.url)

            clear_cart()
            return redirect(url_for("public.checkout_confirmation", order_number=order.order_number))

    summary = build_cart_summary(
        current_app.config,
        fulfillment_method=form.fulfillment_method.data or "pickup",
    )
    return render_template(
        "public/checkout.html",
        form=form,
        summary=summary,
        square_enabled=square_enabled,
        venmo_handle=current_app.config.get("SHOP_VENMO_HANDLE"),
    )


@bp.get("/checkout/confirmation/<order_number>")
def checkout_confirmation(order_number: str):
    order = Order.query.filter_by(order_number=order_number, source=OrderSource.ONLINE).first()
    if order is None:
        abort(404)
    return render_template("public/checkout_confirmation.html", order=order)


@bp.route("/custom-orders", methods=["GET", "POST"])
def custom_orders():
    form = PublicCustomRequestForm()
    if form.validate_on_submit():
        custom_req = CustomRequest(
            name=form.name.data.strip(),
            email=form.email.data.strip(),
            phone=form.phone.data.strip() if form.phone.data else None,
            description=form.description.data,
            estimated_budget=form.estimated_budget.data.strip() if form.estimated_budget.data else None,
            source="website",
        )
        create_custom_request(custom_req, actor_type="anonymous")
        flash("Thanks! We'll review your request and get back to you soon.", "success")
        return render_template("public/custom_orders.html", form=PublicCustomRequestForm(), submitted=True)
    return render_template("public/custom_orders.html", form=form, submitted=False)


@bp.get("/small-business-products")
def small_business_products():
    return render_template("public/small_business_products.html")


@bp.get("/military-family-gifts")
def military_family_gifts():
    return render_template("public/military_family_gifts.html")


@bp.get("/market-schedule")
def market_schedule():
    markets = Market.query.filter(
        Market.status.in_([MarketStatus.SCHEDULED, MarketStatus.ACCEPTED, MarketStatus.INTERESTED])
    ).order_by(Market.event_date.asc()).all()
    return render_template("public/market_schedule.html", markets=markets)


@bp.get("/3d-printing-basics")
def printing_basics():
    return render_template("public/printing_basics.html")


@bp.get("/returns")
def returns():
    return render_template("public/returns.html")


@bp.get("/customer-policies")
def customer_policies():
    return render_template("public/customer_policies.html")


@bp.get("/privacy")
def privacy():
    return render_template("public/privacy.html")


@bp.get("/terms")
def terms():
    return render_template("public/terms.html")


@bp.get("/gallery")
def gallery():
    products = db.session.scalars(_public_product_query().order_by(Product.name.asc()).limit(18)).all()
    return render_template("public/gallery.html", products=products)


@bp.get("/accessibility")
def accessibility():
    return render_template("public/accessibility.html")


@bp.get("/shipping-policy")
def shipping_policy():
    return render_template("public/shipping_policy.html")


@bp.get("/collections/<slug>")
def collection_detail(slug: str):
    collection = Collection.query.filter_by(slug=slug, is_public=True).first()
    if collection is None:
        abort(404)

    products = (
        Product.query.filter_by(collection_id=collection.id, is_public=True)
        .filter(Product.deleted_at.is_(None), Product.status == ProductStatus.ACTIVE)
        .order_by(Product.name.asc())
        .all()
    )
    return render_template(
        "public/collection_detail.html",
        collection=collection,
        products=products,
        available_stock_label=available_stock_label,
    )
