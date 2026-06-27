from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from flask import (
    abort,
    current_app,
    flash,
    g,
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
from app.forms.studio import ModelAssetUploadForm, ProductStudioForm, VariantInlineForm
from app.models import (
    Category,
    Collection,
    ModelAsset,
    Product,
    ProductImage,
    ProductStatus,
    ProductVariant,
    UserRole,
)
from app.services.admin_mutations import (
    create_resource as create_admin_resource,
    snapshot_instance,
    update_resource as update_admin_resource,
)
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


def _preferred_image_filename(product: Product, original_filename: str, *, variant_id: int | None) -> str:
    existing_names = {
        storage_reference_name(image.file_path)
        for image in product.images
        if image.variant_id == variant_id and image.file_path
    }
    return _unique_storage_filename(existing_names, original_filename)


def _variant_form_for(variant: ProductVariant) -> VariantInlineForm:
    form = VariantInlineForm(prefix=f"variant-{variant.id}")
    form.load_from_variant(variant)
    return form


@bp.route("/studio", methods=["GET", "POST"])
@bp.route("/studio/<int:product_id>", methods=["GET", "POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def studio(product_id: int | None = None):
    product = get_by_id(Product, product_id) if product_id else None
    form = ProductStudioForm()
    mode = "edit" if product else "create"

    categories = Category.query.order_by(Category.name).all()
    collections = Collection.query.order_by(Collection.name).all()

    if form.validate_on_submit():
        if product is None:
            product = Product()
            product.business_id = 1
            form.populate_product(product)
            try:
                product = create_admin_resource(product, actor_id=current_user.id)
            except IntegrityError:
                db.session.rollback()
                flash("Unable to save that product. Please check for duplicates.", "danger")
                return render_template(
                    "products/studio.html",
                    form=form,
                    product=product,
                    mode=mode,
                    categories=categories,
                    collections=collections,
                    model_assets=[],
                    variants=[],
                )
            flash("Product created successfully.", "success")
            return redirect(url_for("products.studio", product_id=product.id))
        else:
            before_state = snapshot_instance(product)
            form.populate_product(product)
            try:
                update_admin_resource(product, before_state=before_state, actor_id=current_user.id)
            except IntegrityError:
                db.session.rollback()
                flash("Unable to save that product. Please check for duplicates.", "danger")
                return render_template(
                    "products/studio.html",
                    form=form,
                    product=product,
                    mode=mode,
                    categories=categories,
                    collections=collections,
                    model_assets=product.model_assets,
                    variants=product.variants,
                )
            flash("Product updated successfully.", "success")
            return redirect(url_for("products.studio", product_id=product.id))

    if product:
        form.load_from_product(product)
    else:
        form.status.data = ProductStatus.DRAFT.value

    model_assets = product.model_assets if product else []
    variants = product.variants if product else []
    product_images = [img for img in (product.images if product else []) if img.variant_id is None]
    primary_assets = [asset for asset in model_assets if asset.variant_id is None]
    variant_forms = {variant.id: _variant_form_for(variant) for variant in variants}

    return render_template(
        "products/studio.html",
        form=form,
        product=product,
        mode=mode,
        categories=categories,
        collections=collections,
        model_assets=model_assets,
        variants=variants,
        product_images=product_images,
        primary_assets=primary_assets,
        variant_forms=variant_forms,
        storage_reference_name=storage_reference_name,
    )


@bp.route("/studio/<int:product_id>/upload-model", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def upload_model(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        abort(404)

    upload_form = ModelAssetUploadForm()
    if not upload_form.validate_on_submit():
        errors = []
        for field, field_errors in upload_form.errors.items():
            for err in field_errors:
                errors.append(f"{field}: {err}")
        return (
            jsonify({"success": False, "error": "; ".join(errors)}),
            400,
        )

    file = upload_form.model_file.data
    if not file:
        return jsonify({"success": False, "error": "No file provided"}), 400

    variant_id = request.form.get("variant_id", type=int)
    if variant_id is not None:
        v = db.session.get(ProductVariant, variant_id)
        if v is None or v.product_id != product.id:
            return jsonify({"success": False, "error": "Invalid variant"}), 400

    ext = Path(file.filename).suffix.lower()
    safe_filename = normalize_storage_filename(f"{uuid.uuid4().hex}{ext}")
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    key = product_storage_key(product.id, safe_filename, variant_id=variant_id)

    data = file.read()
    content_type = content_type_for_name(file.filename, "application/octet-stream")

    storage_ref = upload_bytes_to_storage(
        data,
        bucket=bucket,
        key=key,
        local_root=local_root,
        content_type=content_type,
    )

    asset = ModelAsset()
    upload_form.populate_asset(asset)
    asset.file_location = storage_ref
    asset.related_product_id = product.id
    asset.variant_id = variant_id
    asset.analysis_status = "pending"
    asset.analysis_requested_at = datetime.now(timezone.utc)
    db.session.add(asset)
    db.session.commit()

    celery = _get_celery()
    if celery is not None:
        from app.tasks.model_analysis import analyze_model_asset
        task = analyze_model_asset.delay(asset.id)
        task_id = task.id
    else:
        task_id = None

    return jsonify(
        {
            "success": True,
            "asset_id": asset.id,
            "task_id": task_id,
            "file_location": storage_ref,
        }
    )


@bp.route("/studio/variant-cost/<int:variant_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def calculate_variant_cost(variant_id: int):
    variant = get_by_id(ProductVariant, variant_id)
    if variant is None:
        return jsonify({"success": False, "error": "Variant not found"}), 404

    celery = _get_celery()
    if celery is not None:
        from app.tasks.cost_calculation import calculate_variant_cost_task
        task = calculate_variant_cost_task.delay(variant_id)
        return jsonify({"success": True, "task_id": task.id})
    else:
        breakdown = calculate_product_cost(
            product=variant.product,
            variant=variant,
            sale_price=variant.price,
        )
        variant.material_cost = breakdown.material_cost
        variant.estimated_filament_grams = int(round(float(breakdown.filament_grams)))
        variant.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
        persist_cost_snapshot(
            product=variant.product,
            variant=variant,
            breakdown=breakdown,
            snapshot_reason="studio.variant",
        )
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "total_cost": str(breakdown.total_cost),
                "suggested_price": str(breakdown.suggested_price),
                "margin_percent": str(breakdown.margin_percent),
                "material_cost": str(breakdown.material_cost),
                "snapshot_id": breakdown.snapshot_id,
            }
        )


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
    else:
        breakdown = calculate_product_cost(product=product)
        product.estimated_material_cost = breakdown.material_cost
        product.estimated_profit = breakdown.margin_dollars
        product.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
        persist_cost_snapshot(
            product=product,
            variant=None,
            breakdown=breakdown,
            snapshot_reason="studio.product",
        )
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "total_cost": str(breakdown.total_cost),
                "suggested_price": str(breakdown.suggested_price),
                "margin_percent": str(breakdown.margin_percent),
                "material_cost": str(breakdown.material_cost),
                "labor_cost": str(breakdown.labor_cost),
                "machine_cost": str(breakdown.machine_cost),
                "snapshot_id": breakdown.snapshot_id,
            }
        )


@bp.route("/studio/create-variant/<int:product_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def create_variant(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        abort(404)

    form = VariantInlineForm()
    if form.validate_on_submit():
        variant = ProductVariant()
        variant.product_id = product.id
        variant.business_id = product.business_id or 1
        form.populate_variant(variant)

        try:
            create_admin_resource(variant, actor_id=current_user.id)
        except IntegrityError:
            db.session.rollback()
            return jsonify({"success": False, "error": "A variant with that SKU already exists."}), 400

        breakdown = calculate_product_cost(product=product, variant=variant)
        variant.material_cost = breakdown.material_cost
        variant.estimated_filament_grams = int(round(float(breakdown.filament_grams)))
        variant.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
        persist_cost_snapshot(
            product=product,
            variant=variant,
            breakdown=breakdown,
            snapshot_reason="studio.create_variant",
        )
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "variant_id": variant.id,
                "sku": variant.sku,
                "name": variant.name,
                "price": str(variant.price),
                "material_cost": str(breakdown.material_cost),
                "total_cost": str(breakdown.total_cost),
                "margin_percent": str(breakdown.margin_percent),
                "suggested_price": str(breakdown.suggested_price),
                "active": variant.active,
                "snapshot_id": breakdown.snapshot_id,
            }
        )

    errors = []
    for field, field_errors in form.errors.items():
        for err in field_errors:
            errors.append(f"{field}: {err}")
    return jsonify({"success": False, "error": "; ".join(errors)}), 400


@bp.route("/studio/update-variant/<int:variant_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def update_variant(variant_id: int):
    variant = get_by_id(ProductVariant, variant_id)
    if variant is None:
        abort(404)

    form = VariantInlineForm(prefix=f"variant-{variant.id}")
    if not form.validate_on_submit():
        errors = []
        for field, field_errors in form.errors.items():
            for err in field_errors:
                errors.append(f"{field}: {err}")
        flash("; ".join(errors) or "Unable to update variant.", "danger")
        return redirect(url_for("products.studio", product_id=variant.product_id))

    before_state = snapshot_instance(variant)
    form.populate_variant(variant)
    try:
        update_admin_resource(variant, before_state=before_state, actor_id=current_user.id)
    except IntegrityError:
        db.session.rollback()
        flash("Unable to save that variant. Please check for duplicate SKUs.", "danger")
        return redirect(url_for("products.studio", product_id=variant.product_id))

    flash(f"{variant.name} updated.", "success")
    return redirect(url_for("products.studio", product_id=variant.product_id))


@bp.route("/studio/delete-variant/<int:variant_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def delete_variant(variant_id: int):
    variant = get_by_id(ProductVariant, variant_id)
    if variant is None:
        return jsonify({"success": False, "error": "Variant not found"}), 404

    product_id = variant.product_id
    db.session.delete(variant)
    db.session.commit()
    flash("Variant deleted.", "success")
    return redirect(url_for("products.studio", product_id=product_id))


@bp.route("/studio/delete-model/<int:asset_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def delete_model(asset_id: int):
    asset = get_by_id(ModelAsset, asset_id)
    if asset is None:
        return jsonify({"success": False, "error": "Model asset not found"}), 404

    product_id = asset.related_product_id
    db.session.delete(asset)
    db.session.commit()
    flash("Model asset deleted.", "success")
    return redirect(url_for("products.studio", product_id=product_id))


@bp.route("/studio/reanalyze/<int:asset_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def reanalyze_model(asset_id: int):
    asset = get_by_id(ModelAsset, asset_id)
    if asset is None:
        return jsonify({"success": False, "error": "Model asset not found"}), 404

    asset.analysis_status = "pending"
    asset.analysis_error = None
    asset.analysis_completed_at = None
    asset.analysis_requested_at = datetime.now(timezone.utc)
    db.session.commit()

    celery = _get_celery()
    task_id = None
    if celery is not None:
        from app.tasks.model_analysis import analyze_model_asset
        task = analyze_model_asset.delay(asset.id)
        task_id = task.id

    return jsonify({"success": True, "task_id": task_id, "asset_id": asset.id})


@bp.route("/studio/task-status/<task_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def task_status(task_id: str):
    celery = _get_celery()
    if celery is None:
        return jsonify({"state": "NO_CELERY", "result": None})

    result = celery.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.info) if result.info else "Unknown error"
        response["traceback"] = str(result.traceback) if result.traceback else None
    elif result.state == "PENDING":
        response["info"] = "Task has not started yet."
    elif result.state == "PROGRESS" or result.state == "STARTED":
        response["info"] = result.info if result.info else "Processing..."

    return jsonify(response)


@bp.route("/studio/<int:asset_id>/download-model")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def download_model(asset_id: int):
    asset = get_by_id(ModelAsset, asset_id)
    if asset is None or not asset.file_location:
        abort(404)

    ref = asset.converted_model_path or asset.file_location
    download_name = storage_reference_name(ref)

    if is_s3_reference(ref):
        from app.services.storage import download_storage_bytes
        data = download_storage_bytes(ref)
        mime = content_type_for_name(download_name, "model/gltf-binary" if download_name.endswith(".glb") else "application/octet-stream")
        return send_file(
            io.BytesIO(data),
            download_name=download_name,
            mimetype=mime,
        )
    else:
        mime = content_type_for_name(download_name)
        return send_file(ref, download_name=download_name, mimetype=mime)


@bp.route("/studio/<int:asset_id>/view-model")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def view_model(asset_id: int):
    asset = get_by_id(ModelAsset, asset_id)
    if asset is None or not asset.file_location:
        abort(404)

    ref = asset.converted_model_path or asset.file_location
    download_name = storage_reference_name(ref)
    mime = content_type_for_name(download_name)

    if is_s3_reference(ref):
        from app.services.storage import download_storage_bytes
        import io
        data = download_storage_bytes(ref)
        return send_file(
            io.BytesIO(data),
            mimetype=mime,
            download_name=download_name,
        )
    else:
        return send_file(ref, mimetype=mime)


@bp.route("/studio/<int:asset_id>/analysis-result")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def analysis_result(asset_id: int):
    asset = get_by_id(ModelAsset, asset_id)
    if asset is None:
        return jsonify({"success": False, "error": "Not found"}), 404

    return jsonify(
        {
            "success": True,
            "asset_id": asset.id,
            "status": asset.analysis_status,
            "error": asset.analysis_error,
            "volume_mm3": float(asset.parsed_volume_mm3) if asset.parsed_volume_mm3 else None,
            "surface_area_mm2": float(asset.parsed_surface_area_mm2) if asset.parsed_surface_area_mm2 else None,
            "triangle_count": asset.parsed_triangle_count,
            "filament_grams": float(asset.parsed_filament_grams) if asset.parsed_filament_grams else None,
            "print_minutes": float(asset.parsed_print_minutes) if asset.parsed_print_minutes else None,
            "material_cost": str(asset.parsed_material_cost) if asset.parsed_material_cost else None,
            "convert_status": asset.convert_status,
            "converted_model_path": asset.converted_model_path,
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

    variant_id = request.form.get("variant_id", type=int)
    if variant_id is not None:
        v = db.session.get(ProductVariant, variant_id)
        if v is None or v.product_id != product.id:
            return jsonify({"success": False, "error": "Invalid variant"}), 400

    file = request.files.get("image")
    if not file:
        return jsonify({"success": False, "error": "No image file provided"}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return jsonify({"success": False, "error": "Unsupported image type. Use JPG, PNG, WebP, or GIF."}), 400

    safe_filename = _preferred_image_filename(
        product,
        file.filename or f"image{ext}",
        variant_id=variant_id,
    )
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    key = image_storage_key(product.id, safe_filename, variant_id=variant_id)

    data = file.read()
    content_type = content_type_for_name(file.filename, "image/jpeg")

    storage_ref = upload_bytes_to_storage(
        data,
        bucket=bucket,
        key=key,
        local_root=local_root,
        content_type=content_type,
    )

    img = ProductImage(
        product_id=product.id,
        variant_id=variant_id,
        file_path=storage_ref,
        alt_text=request.form.get("alt_text", ""),
    )

    is_first = not ProductImage.query.filter_by(product_id=product.id, variant_id=variant_id).first()
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

    return jsonify({
        "success": True,
        "image_id": img.id,
        "file_path": storage_ref,
        "is_default": img.is_default,
        "is_pos": img.is_pos,
        "url": url_for("products.serve_product_image", image_id=img.id),
    })


@bp.route("/studio/set-default-image/<int:image_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def set_default_image(image_id: int):
    img = db.session.get(ProductImage, image_id)
    if img is None:
        return jsonify({"success": False, "error": "Image not found"}), 404

    ProductImage.query.filter_by(product_id=img.product_id, variant_id=img.variant_id).update({"is_default": False})
    img.is_default = True
    product = img.product
    if product:
        product.default_image_path = img.file_path
    db.session.commit()
    return jsonify({"success": True})


@bp.route("/studio/set-pos-image/<int:image_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def set_pos_image(image_id: int):
    img = db.session.get(ProductImage, image_id)
    if img is None:
        return jsonify({"success": False, "error": "Image not found"}), 404

    ProductImage.query.filter_by(product_id=img.product_id, variant_id=img.variant_id).update({"is_pos": False})
    img.is_pos = True
    product = img.product
    if product:
        product.pos_image_path = img.file_path
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
        import io
        data = download_storage_bytes(ref)
        return send_file(
            io.BytesIO(data),
            mimetype=mime,
            download_name=download_name,
        )
    return send_file(ref, mimetype=mime)


@bp.route("/studio/rename-file", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def rename_file():
    data = request.get_json(force=True)
    file_type = data.get("type")
    file_id = data.get("id", type=int)
    new_title = (data.get("title") or "").strip()

    if not file_type or not file_id or not new_title:
        return jsonify({"success": False, "error": "type, id, and title are required"}), 400

    if file_type == "model":
        asset = db.session.get(ModelAsset, file_id)
        if not asset:
            return jsonify({"success": False, "error": "Model asset not found"}), 404
        asset.title = new_title
    elif file_type == "image":
        img = db.session.get(ProductImage, file_id)
        if not img:
            return jsonify({"success": False, "error": "Image not found"}), 404
        img.alt_text = new_title
    else:
        return jsonify({"success": False, "error": f"Unknown file type: {file_type}"}), 400

    db.session.commit()
    return jsonify({"success": True})


@bp.route("/studio/<int:product_id>/files")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def product_file_list(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        return jsonify({"success": False, "error": "Not found"}), 404

    files = []

    for asset in product.model_assets:
        entry = {
            "id": asset.id,
            "type": "model",
            "title": asset.title,
            "variant_id": asset.variant_id,
        }
        if asset.file_location:
            entry["file_path"] = asset.file_location
            entry["filename"] = storage_reference_name(asset.file_location)
            entry["download_url"] = url_for("products.download_model", asset_id=asset.id)
            entry["view_url"] = url_for("products.view_model", asset_id=asset.id) if asset.file_location else None
        if asset.converted_model_path:
            entry["converted_path"] = asset.converted_model_path
        if asset.gcode_path:
            entry["gcode_path"] = asset.gcode_path
            entry["gcode_filename"] = storage_reference_name(asset.gcode_path)
        entry["analysis_status"] = asset.analysis_status
        files.append(entry)

    for img in product.images:
        files.append({
            "id": img.id,
            "type": "image",
            "variant_id": img.variant_id,
            "file_path": img.file_path,
            "filename": storage_reference_name(img.file_path),
            "is_default": img.is_default,
            "is_pos": img.is_pos,
            "alt_text": img.alt_text,
            "view_url": url_for("products.serve_product_image", image_id=img.id),
            "download_url": url_for("products.serve_product_image", image_id=img.id),
        })

    return jsonify({"success": True, "files": files})
