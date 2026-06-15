from __future__ import annotations

from flask import abort, flash, render_template, request
from sqlalchemy import select

from app.blueprints.public import bp
from app.extensions import db
from app.forms import PublicCustomRequestForm
from app.models import Category, Collection, CustomRequest, Product, ProductStatus
from app.services.crud import save_instance


@bp.get("/")
def home():
    return render_template("public/home.html")


@bp.get("/shop")
def shop():
    category_slug = request.args.get("category", "").strip()
    collection_slug = request.args.get("collection", "").strip()
    search_term = request.args.get("q", "").strip()

    statement = select(Product).where(
        Product.is_public.is_(True),
        Product.deleted_at.is_(None),
        Product.status == ProductStatus.ACTIVE,
    )

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
    )


@bp.get("/shop/<slug>")
def product_detail(slug: str):
    product = Product.query.filter_by(slug=slug, is_public=True).first()
    if product is None or product.deleted_at is not None:
        abort(404)
    return render_template("public/product_detail.html", product=product)


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
        save_instance(custom_req)
        flash("Thanks! We'll review your request and get back to you soon.", "success")
        return render_template("public/custom_orders.html", form=PublicCustomRequestForm(), submitted=True)
    return render_template("public/custom_orders.html", form=form, submitted=False)


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
        "public/collection_detail.html", collection=collection, products=products
    )
