from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app.blueprints.products import bp
from app.extensions import db
from app.forms.studio import ProductModelUploadForm, ProductStudioForm
from app.models import Category, Collection, Product, ProductImage, ProductStatus, UserRole
from app.services.admin_mutations import (
    create_resource as create_admin_resource,
    snapshot_instance,
    update_resource as update_admin_resource,
)
from app.services.audit_client import get_audit_client
from app.services.business import ensure_default_business
from app.services.cost_engine import build_pricing_scenarios, calculate_product_cost, persist_cost_snapshot
from app.services.crud import get_by_id
from app.services.storage import (
    content_type_for_name,
    image_storage_key,
    is_s3_reference,
    normalize_storage_filename,
    product_storage_key,
    storage_reference_name,
    upload_bytes_to_storage,
)
from app.utils.auth import roles_required


def _get_celery():
    from app.celery_app import celery as _celery_instance

    return _celery_instance


def _load_products() -> list[Product]:
    return (
        Product.query.filter(Product.deleted_at.is_(None))
        .order_by(Product.updated_at.desc(), Product.name.asc())
        .all()
    )


def _unique_storage_filename(existing_names: set[str], desired_name: str) -> str:
    normalized = normalize_storage_filename(desired_name)
    if normalized not in existing_names:
        return normalized

    path = Path(normalized)
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = f"{stem}-{counter}{suffix}"
        if candidate not in existing_names:
            return candidate
        counter += 1


def _preferred_image_filename(product: Product, original_filename: str) -> str:
    existing_names = {
        storage_reference_name(image.file_path)
        for image in product.images
        if image.file_path
    }
    return _unique_storage_filename(existing_names, original_filename)


def _render_studio(product: Product | None, form: ProductStudioForm, mode: str, status_code: int = 200):
    return (
        render_template(
            "products/studio.html",
            form=form,
            product=product,
            mode=mode,
            categories=Category.query.order_by(Category.name).all(),
            collections=Collection.query.order_by(Collection.name).all(),
            products=_load_products(),
            product_images=list(product.images) if product else [],
            storage_reference_name=storage_reference_name,
        ),
        status_code,
    )


@bp.route("/studio", methods=["GET", "POST"])
@bp.route("/studio/<int:product_id>", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def studio(product_id: int | None = None):
    product = get_by_id(Product, product_id) if product_id else None
    form = ProductStudioForm()
    mode = "edit" if product else "create"

    if product:
        form.instance_id = product.id

    if form.validate_on_submit():
        if product is None:
            business = ensure_default_business()
            product = Product()
            product.business_id = business.id
            form.populate_product(product)
            try:
                product = create_admin_resource(product, actor_id=current_user.id)
            except IntegrityError:
                db.session.rollback()
                flash("Unable to save that product. Please check for duplicates.", "danger")
                return _render_studio(None, form, "create", 400)
            flash("Product created successfully.", "success")
            return redirect(url_for("products.studio", product_id=product.id))

        before_state = snapshot_instance(product)
        form.populate_product(product)
        try:
            update_admin_resource(product, before_state=before_state, actor_id=current_user.id)
        except IntegrityError:
            db.session.rollback()
            flash("Unable to save that product. Please check for duplicates.", "danger")
            return _render_studio(product, form, mode, 400)
        flash("Product updated successfully.", "success")
        return redirect(url_for("products.studio", product_id=product.id))

    if request.method == "GET":
        if product:
            form.load_from_product(product)
        else:
            form.status.data = ProductStatus.DRAFT.value

    return _render_studio(product, form, mode)


@bp.route("/studio/<int:product_id>/upload-model", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def upload_model(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        abort(404)

    upload_form = ProductModelUploadForm()
    if not upload_form.validate_on_submit():
        errors = []
        for field, field_errors in upload_form.errors.items():
            for err in field_errors:
                errors.append(f"{field}: {err}")
        return jsonify({"success": False, "error": "; ".join(errors)}), 400

    file = upload_form.model_file.data
    if not file:
        return jsonify({"success": False, "error": "No file provided"}), 400

    ext = Path(file.filename).suffix.lower()
    safe_filename = normalize_storage_filename(f"{uuid.uuid4().hex}{ext}")
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    key = product_storage_key(product.id, safe_filename)
    content_type = content_type_for_name(file.filename, "application/octet-stream")
    storage_ref = upload_bytes_to_storage(
        file.read(),
        bucket=bucket,
        key=key,
        local_root=local_root,
        content_type=content_type,
    )

    product.model_file_path = storage_ref
    product.analysis_status = "pending"
    product.analysis_error = None
    product.analysis_requested_at = datetime.now(timezone.utc)
    product.analysis_completed_at = None
    product.convert_status = None
    product.conversion_error = None
    product.converted_model_path = None
    product.gcode_path = None
    db.session.commit()

    celery = _get_celery()
    task_id = None
    if celery is not None:
        from app.tasks.model_analysis import analyze_product_model

        task = analyze_product_model.delay(product.id)
        task_id = task.id

    return jsonify({"success": True, "product_id": product.id, "task_id": task_id, "file_location": storage_ref})


@bp.route("/studio/<int:product_id>/calculate-costs", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def calculate_product_costs(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        return jsonify({"success": False, "error": "Product not found"}), 404

    celery = _get_celery()
    if celery is not None:
        from app.tasks.cost_calculation import calculate_product_cost_task

        task = calculate_product_cost_task.delay(product_id)
        return jsonify({"success": True, "task_id": task.id})

    breakdown = calculate_product_cost(product=product)
    product.estimated_material_cost = breakdown.material_cost
    product.estimated_profit = breakdown.margin_dollars
    product.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
    persist_cost_snapshot(product=product, breakdown=breakdown, snapshot_reason="studio.product")
    db.session.commit()
    return jsonify(
        {
            "success": True,
            "total_cost": str(breakdown.total_cost),
            "suggested_price": str(breakdown.suggested_price),
            "margin_percent": str(breakdown.margin_percent),
            "margin_dollars": str(breakdown.margin_dollars),
            "material_cost": str(breakdown.material_cost),
            "filament_grams": str(breakdown.filament_grams),
            "print_minutes": str(breakdown.print_minutes),
            "snapshot_id": breakdown.snapshot_id,
        }
    )


@bp.route("/studio/task-status/<task_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def task_status(task_id: str):
    celery = _get_celery()
    if celery is None:
        return jsonify({"state": "NO_CELERY", "result": None})

    result = celery.AsyncResult(task_id)
    response = {"task_id": task_id, "state": result.state}
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.info) if result.info else "Unknown error"
        response["traceback"] = str(result.traceback) if result.traceback else None
    elif result.state == "PENDING":
        response["info"] = "Task has not started yet."
    elif result.state in {"PROGRESS", "STARTED"}:
        response["info"] = result.info if result.info else "Processing..."
    return jsonify(response)


@bp.route("/studio/<int:product_id>/download-model")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def download_model(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None or not product.model_file_path:
        abort(404)

    ref = product.converted_model_path or product.model_file_path
    download_name = storage_reference_name(ref)
    mime = content_type_for_name(download_name, "application/octet-stream")

    if is_s3_reference(ref):
        from app.services.storage import download_storage_bytes

        data = download_storage_bytes(ref)
        return send_file(io.BytesIO(data), download_name=download_name, mimetype=mime)
    return send_file(ref, download_name=download_name, mimetype=mime)


@bp.route("/studio/<int:product_id>/view-model")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def view_model(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None or not product.model_file_path:
        abort(404)

    ref = product.converted_model_path or product.model_file_path
    download_name = storage_reference_name(ref)
    mime = content_type_for_name(download_name)
    if is_s3_reference(ref):
        from app.services.storage import download_storage_bytes

        data = download_storage_bytes(ref)
        return send_file(io.BytesIO(data), mimetype=mime, download_name=download_name)
    return send_file(ref, mimetype=mime)


@bp.route("/studio/reanalyze/<int:product_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def reanalyze_model(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        return jsonify({"success": False, "error": "Product not found"}), 404

    product.analysis_status = "pending"
    product.analysis_error = None
    product.analysis_completed_at = None
    product.analysis_requested_at = datetime.now(timezone.utc)
    db.session.commit()

    celery = _get_celery()
    task_id = None
    if celery is not None:
        from app.tasks.model_analysis import analyze_product_model

        task = analyze_product_model.delay(product.id)
        task_id = task.id

    return jsonify({"success": True, "task_id": task_id, "product_id": product.id})


@bp.route("/studio/<int:product_id>/analysis-result")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def analysis_result(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        return jsonify({"success": False, "error": "Not found"}), 404

    return jsonify(
        {
            "success": True,
            "product_id": product.id,
            "status": product.analysis_status,
            "error": product.analysis_error,
            "volume_mm3": float(product.parsed_volume_mm3) if product.parsed_volume_mm3 else None,
            "surface_area_mm2": float(product.parsed_surface_area_mm2) if product.parsed_surface_area_mm2 else None,
            "triangle_count": product.parsed_triangle_count,
            "filament_grams": float(product.parsed_filament_grams) if product.parsed_filament_grams else None,
            "print_minutes": float(product.parsed_print_minutes) if product.parsed_print_minutes else None,
            "material_cost": str(product.parsed_material_cost) if product.parsed_material_cost else None,
            "convert_status": product.convert_status,
            "converted_model_path": product.converted_model_path,
        }
    )


@bp.route("/studio/cost-result/<int:product_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def cost_result(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        return jsonify({"success": False, "error": "Not found"}), 404

    breakdown = calculate_product_cost(product=product)
    return jsonify(
        {
            "success": True,
            "material_cost": str(breakdown.material_cost),
            "filament_grams": str(breakdown.filament_grams),
            "labor_cost": str(breakdown.labor_cost),
            "machine_cost": str(breakdown.machine_cost),
            "packaging_cost": str(breakdown.packaging_cost),
            "payment_fees": str(breakdown.payment_fees),
            "failure_adjustment": str(breakdown.failure_adjustment),
            "total_cost": str(breakdown.total_cost),
            "suggested_price": str(breakdown.suggested_price),
            "margin_dollars": str(breakdown.margin_dollars),
            "margin_percent": str(breakdown.margin_percent),
            "evidence_source": breakdown.evidence_source,
            "confidence": breakdown.confidence,
            "cost_per_gram": str(breakdown.cost_per_gram),
            "model_volume_cm3": str(breakdown.model_volume_cm3),
            "profit_per_print_hour": str(breakdown.profit_per_print_hour),
            "profit_per_market_bin_cm3": str(breakdown.profit_per_market_bin_cm3),
            "pricing_scenarios": build_pricing_scenarios(product=product),
        }
    )


@bp.route("/studio/<int:product_id>/upload-image", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def upload_product_image(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        abort(404)

    file = request.files.get("image")
    if not file:
        return jsonify({"success": False, "error": "No image file provided"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return jsonify({"success": False, "error": "Unsupported image type. Use JPG, PNG, WebP, or GIF."}), 400

    safe_filename = _preferred_image_filename(product, file.filename or f"image{ext}")
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    key = image_storage_key(product.id, safe_filename)
    storage_ref = upload_bytes_to_storage(
        file.read(),
        bucket=bucket,
        key=key,
        local_root=local_root,
        content_type=content_type_for_name(file.filename, "image/jpeg"),
    )

    img = ProductImage(
        product_id=product.id,
        file_path=storage_ref,
        alt_text=request.form.get("alt_text", ""),
    )
    is_first = not ProductImage.query.filter_by(product_id=product.id).first()
    if is_first:
        img.is_default = True
        img.is_pos = True
    db.session.add(img)
    db.session.commit()

    if img.is_default:
        product.default_image_path = storage_ref
    if img.is_pos:
        product.pos_image_path = storage_ref
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "image_id": img.id,
            "file_path": storage_ref,
            "is_default": img.is_default,
            "is_pos": img.is_pos,
            "url": url_for("products.serve_product_image", image_id=img.id),
        }
    )


@bp.route("/studio/set-default-image/<int:image_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def set_default_image(image_id: int):
    img = db.session.get(ProductImage, image_id)
    if img is None:
        return jsonify({"success": False, "error": "Image not found"}), 404

    ProductImage.query.filter_by(product_id=img.product_id).update({"is_default": False})
    img.is_default = True
    if img.product:
        img.product.default_image_path = img.file_path
    db.session.commit()
    return jsonify({"success": True})


@bp.route("/studio/set-pos-image/<int:image_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def set_pos_image(image_id: int):
    img = db.session.get(ProductImage, image_id)
    if img is None:
        return jsonify({"success": False, "error": "Image not found"}), 404

    ProductImage.query.filter_by(product_id=img.product_id).update({"is_pos": False})
    img.is_pos = True
    if img.product:
        img.product.pos_image_path = img.file_path
    db.session.commit()
    return jsonify({"success": True})


@bp.route("/studio/delete-image/<int:image_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def delete_product_image(image_id: int):
    img = db.session.get(ProductImage, image_id)
    if img is None:
        return jsonify({"success": False, "error": "Image not found"}), 404

    product = img.product
    if product:
        if product.default_image_path == img.file_path:
            product.default_image_path = None
        if product.pos_image_path == img.file_path:
            product.pos_image_path = None

    db.session.delete(img)
    db.session.commit()
    return jsonify({"success": True})


@bp.route("/studio/serve-image/<int:image_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def serve_product_image(image_id: int):
    img = db.session.get(ProductImage, image_id)
    if img is None or not img.file_path:
        abort(404)

    ref = img.file_path
    download_name = storage_reference_name(ref)
    mime = content_type_for_name(download_name)
    if is_s3_reference(ref):
        from app.services.storage import download_storage_bytes

        data = download_storage_bytes(ref)
        return send_file(io.BytesIO(data), mimetype=mime, download_name=download_name)
    return send_file(ref, mimetype=mime)


@bp.route("/studio/rename-file", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def rename_file():
    data = request.get_json(force=True)
    file_type = data.get("type")
    file_id = int(data.get("id") or 0)
    new_title = (data.get("title") or "").strip()
    if not file_type or not file_id or not new_title:
        return jsonify({"success": False, "error": "type, id, and title are required"}), 400

    if file_type == "model":
        product = db.session.get(Product, file_id)
        if not product:
            return jsonify({"success": False, "error": "Product not found"}), 404
        product.model_notes = new_title
    elif file_type == "image":
        img = db.session.get(ProductImage, file_id)
        if not img:
            return jsonify({"success": False, "error": "Image not found"}), 404
        img.alt_text = new_title
    else:
        return jsonify({"success": False, "error": f"Unknown file type: {file_type}"}), 400

    db.session.commit()
    return jsonify({"success": True})


@bp.route("/studio/<int:product_id>/trend-score", methods=["GET"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def trend_score(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        return jsonify({"success": False, "error": "Product not found"}), 404

    from app.services.ai.trend_scout.analyzer.trend_detector import (
        _catalog_metrics,
        OpportunityCandidate,
        _score_candidate,
        compute_velocity_and_momentum,
    )
    from app.services.trend_match import match_product_to_term

    products = (
        db.session.query(Product)
        .filter(Product.deleted_at.is_(None))
        .all()
    )
    catalog_metrics = _catalog_metrics(db.session)
    _ = compute_velocity_and_momentum(db.session, lookback_weeks=8)

    product_metrics = catalog_metrics.get(product.id, {})
    units_sold = int(product_metrics.get("units_sold", 0))
    revenue = float(product_metrics.get("revenue", 0))

    product_keyword = product.name.lower()
    matched_sources = {"catalog"}
    match_confidence = "exact"

    for other in products:
        if other.id == product.id:
            continue
        matches, confidence = match_product_to_term(product_keyword, other)
        if matches:
            matched_sources.add(other.name.lower())

    candidate = OpportunityCandidate(
        keyword=product_keyword,
        title=product.name,
        current_product=True,
        product_id=product.id,
        product_status=(
            product.status.value if hasattr(product.status, "value") else str(product.status)
        ),
        sources=matched_sources,
        purchase_raw=(units_sold * 10) + (revenue * 0.35),
        inventory_available=int(product.inventory_available or 0),
        reorder_target=int(product.reorder_target or 0),
        units_sold=units_sold,
        online_units_sold=int(product_metrics.get("order_units", 0)),
        pos_units_sold=int(product_metrics.get("pos_units", 0)),
        revenue=revenue,
        base_price=float(product.base_price or 0),
        estimated_profit=float(product.estimated_profit or 0),
        estimated_print_minutes=float(product.parsed_print_minutes or product.estimated_print_minutes or 0),
        license_status=(
            product.license_status.value if hasattr(product.license_status, "value") else str(product.license_status)
        ),
        model_commercial_use_allowed=bool(product.model_commercial_use_allowed),
        is_public=bool(product.is_public),
        is_pos_visible=bool(product.is_pos_visible),
        category=product.category.name if product.category else "",
        tags=product.tags or "",
        match_confidence=match_confidence,
        sell_through_rate=float(product_metrics.get("sell_through_rate", 0.0)),
        days_since_last_sale=int(product_metrics.get("days_since_last_sale", 999)),
        inventory_age_days=int(product_metrics.get("inventory_age_days", 0)),
        stockout_detected=bool(product_metrics.get("stockout_detected", False)),
        margin_pct=float(product_metrics.get("margin_pct", 0.0)),
        last_sale_at=product_metrics.get("last_sale_at"),
        admin_override=product.admin_notes or "",
    )

    if candidate.base_price > 0:
        candidate.prices.append(candidate.base_price)

    scored = _score_candidate(candidate)

    audit = get_audit_client()
    audit.record(
        action="trend_opportunity_score.calculated",
        entity_type="product",
        entity_id=str(product.id),
        actor_id=str(current_user.id),
        actor_type="user",
        actor_display_name=getattr(current_user, "full_name", None) or current_user.email,
        source_module="products.studio_routes",
        after_state={
            "product_name": product.name,
            "opportunity_score": scored.get("opportunity_score"),
            "action": scored.get("action"),
        },
        metadata={
            "source": "product_studio_button",
            "score_breakdown": scored.get("score_breakdown"),
        },
    )

    return jsonify({
        "success": True,
        "product_id": product.id,
        "product_name": product.name,
        "score": scored,
    })
