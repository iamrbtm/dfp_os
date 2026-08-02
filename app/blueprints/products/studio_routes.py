from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path, PurePosixPath

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
from app.models import (
    AssetKind,
    Category,
    Collection,
    ContentDraft,
    CostSnapshot,
    DeadStockRecommendation,
    InternalDemandEvent,
    InventoryMovement,
    InventoryRecord,
    MarketPackingList,
    MarketTablePlacement,
    OrderItem,
    PosSaleItem,
    Product,
    ProductAnalysisRun,
    ProductImage,
    ProductLaunchChecklistItem,
    ProductModelAsset,
    ProductPhotoShot,
    ProductStatus,
    PrintFailureAutopsy,
    PrintJob,
    SignAsset,
    TrendOpportunityScore,
    UserRole,
)
from app.services.admin_mutations import (
    create_resource as create_admin_resource,
    snapshot_instance,
    update_resource as update_admin_resource,
)
from app.services.audit_client import get_audit_client
from app.services.business import ensure_default_business
from app.services.cost_engine import (
    build_pricing_scenarios,
    calculate_product_cost,
    global_cost_defaults,
    persist_cost_snapshot,
)
from app.services.crud import get_by_id
from app.services.product_analysis import (
    create_model_asset,
    current_asset,
    is_analysis_in_progress,
    lock_product_for_analysis,
    reset_product_analysis,
    sanitize_analysis_config,
    start_analysis_run,
)
from app.services.product_ops import (
    accept_dead_stock_recommendation,
    calculate_product_readiness,
    dismiss_dead_stock_recommendation,
    ensure_product_ops_defaults,
    generate_dead_stock_recommendation,
    launch_gate,
    product_inventory_readiness_score,
    retire_product,
    sync_launch_checklist,
    update_checklist_item,
    update_photo_shot,
    update_story_card,
)
from app.services.storage import (
    content_type_for_name,
    delete_storage_reference,
    download_storage_bytes,
    image_storage_key,
    is_analysis_run_asset_name,
    is_s3_reference,
    list_product_assets,
    materialize_storage_reference,
    normalize_storage_filename,
    normalize_product_asset_name,
    product_storage_key,
    send_storage_reference,
    storage_reference_name,
    upload_stream_to_storage,
)
from app.utils.auth import roles_required


def _get_celery():
    from app.celery_app import celery as _celery_instance

    return _celery_instance


def _audit_launch_override(product: Product, override: str, *, actor_id: int) -> None:
    """Record that the launch gate was bypassed with an explicit override (Issue 2/42)."""
    get_audit_client().record(
        action="product.launch_override",
        entity_type="product",
        entity_id=str(product.id),
        actor_id=str(actor_id),
        actor_type="user",
        actor_display_name=getattr(current_user, "display_name", None),
        source_module="products.studio_routes",
        tenant_id=str(product.business_id) if product.business_id else None,
        after_state={"launch_override_reason": override[:2000]},
        metadata={"override_length": len(override)},
    )


def _audit_image_action(image: ProductImage, action: str) -> None:
    """Record a product image lifecycle event (upload/set-default/set-pos/delete)."""
    product = image.product
    get_audit_client().record(
        action=action,
        entity_type="product",
        entity_id=str(product.id) if product else None,
        actor_id=str(current_user.id),
        actor_type="user",
        actor_display_name=getattr(current_user, "display_name", None),
        source_module="products.studio_routes",
        tenant_id=str(product.business_id) if product and product.business_id else None,
        after_state={
            "image_id": image.id,
            "file_path": image.file_path,
            "is_default": image.is_default,
            "is_pos": image.is_pos,
        },
    )


def _load_products() -> list[Product]:
    return (
        Product.query.filter(Product.deleted_at.is_(None))
        .join(Category)
        .order_by(Category.name.asc(), Product.name.asc())
        .all()
    )


def _product_list_groups() -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    by_category: dict[str, dict[str, object]] = {}
    for product in _load_products():
        category_name = product.category.name if product.category else "Uncategorized"
        group = by_category.get(category_name)
        if group is None:
            group = {"category": category_name, "items": []}
            by_category[category_name] = group
            groups.append(group)
        inventory_score, _reason = product_inventory_readiness_score(product)
        base_price = Decimal(str(product.base_price or 0))
        profit = Decimal(str(product.estimated_profit or 0))
        cost = (
            max(Decimal("0"), base_price - profit)
            if profit
            else Decimal(str(product.estimated_material_cost or 0))
        )
        margin = (profit / base_price * Decimal("100")) if base_price > 0 and profit else None
        if inventory_score == Decimal("7"):
            inventory_tone = "success"
        elif inventory_score == Decimal("3.5"):
            inventory_tone = "warning"
        else:
            inventory_tone = "danger"
        group["items"].append(
            {
                "product": product,
                "inventory_score": inventory_score,
                "inventory_tone": inventory_tone,
                "inventory": sum(record.quantity_on_hand for record in product.inventory_records),
                "sale_price": base_price,
                "cost": cost,
                "margin": margin,
            }
        )
    return groups


def _product_cost_summary(product: Product | None) -> dict[str, Decimal | None | str]:
    if product is None:
        return {
            "base_price": Decimal("0"),
            "unit_cost": Decimal("0"),
            "margin": None,
            "tone": "muted",
        }
    base_price = Decimal(str(product.base_price or 0))
    profit = Decimal(str(product.estimated_profit or 0))
    unit_cost = (
        max(Decimal("0"), base_price - profit)
        if profit
        else Decimal(str(product.estimated_material_cost or 0))
    )
    margin = (profit / base_price * Decimal("100")) if base_price > 0 and profit else None
    if margin is None:
        tone = "muted"
    elif margin >= Decimal("50"):
        tone = "success"
    elif margin >= Decimal("30"):
        tone = "warning"
    else:
        tone = "danger"
    return {"base_price": base_price, "unit_cost": unit_cost, "margin": margin, "tone": tone}


def _decimal_from_payload(data: dict, key: str) -> Decimal | None:
    value = data.get(key)
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _int_from_payload(data: dict, key: str) -> int | None:
    value = data.get(key)
    if value in (None, ""):
        return None
    return int(value)


def _cost_preview_payload(breakdown, *, sale_price: Decimal) -> dict[str, str | None]:
    return {
        "base_price": str(sale_price),
        "material_cost": str(breakdown.material_cost),
        "filament_grams": str(breakdown.filament_grams),
        "cost_per_gram": str(breakdown.cost_per_gram),
        "labor_minutes": str(breakdown.labor_minutes),
        "labor_cost": str(breakdown.labor_cost),
        "print_minutes": str(breakdown.print_minutes),
        "machine_cost": str(breakdown.machine_cost),
        "packaging_cost": str(breakdown.packaging_cost),
        "payment_fees": str(breakdown.payment_fees),
        "market_allocation": str(breakdown.market_allocation),
        "failure_adjustment": str(breakdown.failure_adjustment),
        "total_cost": str(breakdown.total_cost),
        "suggested_price": str(breakdown.suggested_price),
        "margin_dollars": str(breakdown.margin_dollars),
        "margin_percent": str(breakdown.margin_percent),
        "profit_per_print_hour": str(breakdown.profit_per_print_hour),
        "confidence": breakdown.confidence,
        "evidence_source": breakdown.evidence_source,
    }


def _delete_product_files(product: Product) -> None:
    refs = {
        product.model_file_path,
        product.model_proof_of_license_path,
        product.converted_model_path,
        product.gcode_path,
        product.model_metadata_path,
    }
    refs.update(image.file_path for image in product.images if image.file_path)
    refs.update(
        asset.storage_reference for asset in product.model_assets if asset.storage_reference
    )
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    refs.update(
        asset["reference"]
        for asset in list_product_assets(product.id, bucket=bucket, local_root=local_root)
    )
    for ref in {ref for ref in refs if ref}:
        delete_storage_reference(ref)


def _delete_product(product: Product) -> None:
    before_state = snapshot_instance(product)
    _delete_product_files(product)

    nullable_product_models = [
        ContentDraft,
        InternalDemandEvent,
        InventoryMovement,
        OrderItem,
        PosSaleItem,
        PrintFailureAutopsy,
        PrintJob,
        SignAsset,
        TrendOpportunityScore,
    ]
    for model in nullable_product_models:
        db.session.query(model).filter(model.product_id == product.id).update(
            {model.product_id: None}, synchronize_session=False
        )

    inventory_record_ids = [record.id for record in product.inventory_records]
    if inventory_record_ids:
        db.session.query(InventoryMovement).filter(
            InventoryMovement.inventory_record_id.in_(inventory_record_ids)
        ).update({InventoryMovement.inventory_record_id: None}, synchronize_session=False)

    db.session.query(MarketPackingList).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )
    db.session.query(MarketTablePlacement).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )
    db.session.query(InventoryRecord).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )
    db.session.query(CostSnapshot).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )
    db.session.query(ProductLaunchChecklistItem).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )
    db.session.query(ProductPhotoShot).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )
    db.session.query(DeadStockRecommendation).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )
    db.session.query(ProductAnalysisRun).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )
    db.session.query(ProductModelAsset).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )
    db.session.query(ProductImage).filter_by(product_id=product.id).delete(
        synchronize_session=False
    )

    product_id = product.id
    business_id = product.business_id
    db.session.delete(product)
    db.session.commit()
    get_audit_client().record(
        action="product.deleted",
        entity_type="product",
        entity_id=str(product_id),
        actor_id=str(current_user.id),
        actor_type="user",
        actor_display_name=getattr(current_user, "display_name", None),
        source_module="products.studio_routes",
        tenant_id=str(business_id) if business_id else None,
        before_state=before_state,
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
        storage_reference_name(image.file_path) for image in product.images if image.file_path
    }
    return _unique_storage_filename(existing_names, original_filename)


def _request_wants_json() -> bool:
    return request.headers.get(
        "X-Requested-With"
    ) == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", "")


def _render_studio(
    product: Product | None,
    form: ProductStudioForm,
    mode: str,
    status_code: int = 200,
    template: str = "products/studio.html",
):
    readiness = None
    launch_items = []
    photo_shots = []
    dead_stock_recommendations = []
    current_analysis_run = None
    if product:
        ensure_product_ops_defaults(product)
        launch_items = sync_launch_checklist(product)
        readiness = calculate_product_readiness(product)
        photo_shots = list(product.photo_shots)
        dead_stock_recommendations = (
            DeadStockRecommendation.query.filter_by(product_id=product.id)
            .order_by(DeadStockRecommendation.created_at.desc())
            .limit(5)
            .all()
        )
        current_analysis_run = (
            next(
                (run for run in product.analysis_runs if run.is_current),
                None,
            )
            or ProductAnalysisRun.query.filter_by(product_id=product.id, is_current=True).first()
        )
        db.session.commit()
    return (
        render_template(
            template,
            form=form,
            product=product,
            mode=mode,
            categories=Category.query.order_by(Category.name).all(),
            collections=Collection.query.order_by(Collection.name).all(),
            product_groups=_product_list_groups(),
            product_images=list(product.images) if product else [],
            upload_form=ProductModelUploadForm(),
            readiness=readiness,
            cost_summary=_product_cost_summary(product),
            launch_items=launch_items,
            photo_shots=photo_shots,
            dead_stock_recommendations=dead_stock_recommendations,
            current_analysis_run=current_analysis_run,
            storage_reference_name=storage_reference_name,
            cost_defaults=global_cost_defaults(),
            ai_story_card_enabled=bool(
                current_app.config.get("AI_PRODUCT_STORY_ENABLED", False)
                and current_app.config.get("OPENAI_API_KEY", "")
            ),
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
            # ---- CREATE (Issue 2): the launch gate must cover new products too ----
            business = ensure_default_business()
            product = Product()
            product.business_id = business.id
            form.populate_product(product)

            used_override = False
            override_text = ""
            is_launching = product.is_public or product.status == ProductStatus.ACTIVE
            if is_launching:
                allowed, blockers = launch_gate(product)
                override = (product.launch_override_reason or "").strip()
                if not allowed:
                    if override:
                        # Override present but insufficient/invalid — block loudly.
                        db.session.rollback()
                        flash(
                            blockers[0] if blockers else "Launch gate blocked this product.",
                            "danger",
                        )
                        for blocker in blockers[:4]:
                            flash(blocker, "warning")
                        return _render_studio(None, form, "create", 400)
                    # No override: new products cannot go live unready — force Draft.
                    product.status = ProductStatus.DRAFT
                    product.is_public = False
                    flash(
                        "New products start as Draft. Add a model, price, license, and photo, "
                        "then publish — or add a 10+ character override reason.",
                        "warning",
                    )
                else:
                    override_text = override
                    used_override = bool(override)

            try:
                product = create_admin_resource(product, actor_id=current_user.id)
            except IntegrityError:
                db.session.rollback()
                flash("Unable to save that product. Please check for duplicates.", "danger")
                return _render_studio(None, form, "create", 400)
            # Audit the override only once the product has an id (Issue 2 step 4).
            if used_override:
                _audit_launch_override(product, override_text, actor_id=current_user.id)
            flash("Product created successfully.", "success")
            return redirect(url_for("products.studio", product_id=product.id))

        # ---- EDIT (Issue 1): stage the change, gate it, commit only if allowed ----
        before_state = snapshot_instance(product)
        form.populate_product(product)
        is_launching = product.is_public or product.status == ProductStatus.ACTIVE
        if is_launching:
            allowed, blockers = launch_gate(product)
            if not allowed:
                # The blocked edit must NOT persist. Roll back the dirty product
                # row and reload the clean version from the database.
                db.session.rollback()
                product = get_by_id(Product, product_id)
                flash(
                    "Product is not launch-ready yet. Complete launch items or add an explicit override reason.",
                    "danger",
                )
                for blocker in blockers[:4]:
                    flash(blocker, "warning")
                return _render_studio(product, form, mode, 400)
            override = (product.launch_override_reason or "").strip()
            if override:
                _audit_launch_override(product, override, actor_id=current_user.id)
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
            # Issue 33 — a product cannot be created without a category to assign it to.
            if not Category.query.first():
                flash(
                    "You need at least one category before you can create a product.",
                    "warning",
                )
        return _render_studio(product, form, mode)

    # Issue 3 — a POST that failed form validation returns 400 (not 200) while
    # still re-rendering the form so the field errors are visible.
    return _render_studio(product, form, mode, 400)


@bp.get("/studio/workspace")
@bp.get("/studio/<int:product_id>/workspace")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def studio_workspace(product_id: int | None = None):
    product = get_by_id(Product, product_id) if product_id else None
    form = ProductStudioForm()
    mode = "edit" if product else "create"
    if product:
        form.instance_id = product.id
        form.load_from_product(product)
    else:
        form.status.data = ProductStatus.DRAFT.value
    return _render_studio(product, form, mode, template="products/_studio_workspace.html")


@bp.route("/studio/<int:product_id>/checklist/<int:item_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def update_launch_checklist_item(product_id: int, item_id: int):
    product = get_by_id(Product, product_id)
    item = ProductLaunchChecklistItem.query.filter_by(id=item_id, product_id=product_id).first()
    if product is None or item is None:
        abort(404)
    item = update_checklist_item(
        item,
        completed=bool(request.form.get("completed")),
        notes=(request.form.get("notes") or "").strip() or None,
        override_reason=(request.form.get("override_reason") or "").strip() or None,
        actor_id=current_user.id,
    )
    if _request_wants_json():
        return jsonify(
            {
                "success": True,
                "item": {
                    "id": item.id,
                    "completed": item.completed,
                    "notes": item.notes,
                    "override_reason": item.override_reason,
                },
            }
        )
    flash("Launch checklist updated.", "success")
    return redirect(url_for("products.studio", product_id=product.id))


@bp.route("/studio/<int:product_id>/photo-shot/<int:shot_id>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def update_product_photo_shot(product_id: int, shot_id: int):
    product = get_by_id(Product, product_id)
    shot = ProductPhotoShot.query.filter_by(id=shot_id, product_id=product_id).first()
    if product is None or shot is None:
        abort(404)
    shot = update_photo_shot(
        shot,
        completed=bool(request.form.get("completed")),
        image_reference=(request.form.get("image_reference") or "").strip() or None,
        notes=(request.form.get("notes") or "").strip() or None,
        actor_id=current_user.id,
    )
    if _request_wants_json():
        return jsonify(
            {
                "success": True,
                "shot": {
                    "id": shot.id,
                    "completed": shot.completed,
                    "image_reference": shot.image_reference,
                    "notes": shot.notes,
                },
            }
        )
    flash("Photo shot list updated.", "success")
    return redirect(url_for("products.studio", product_id=product.id))


@bp.route("/studio/<int:product_id>/story-card", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def update_product_story_card(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        abort(404)
    update_story_card(
        product,
        {
            "story_what_it_is": (request.form.get("story_what_it_is") or "").strip() or None,
            "story_who_it_is_for": (request.form.get("story_who_it_is_for") or "").strip() or None,
            "story_materials": (request.form.get("story_materials") or "").strip() or None,
            "story_customization_options": (
                request.form.get("story_customization_options") or ""
            ).strip()
            or None,
            "story_internal_compliance_notes": (
                request.form.get("story_internal_compliance_notes") or ""
            ).strip()
            or None,
        },
        actor_id=current_user.id,
    )
    flash("Product story card updated.", "success")
    return redirect(url_for("products.studio", product_id=product.id))


@bp.route("/studio/<int:product_id>/story-card/generate", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def generate_product_story_card(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        return jsonify({"success": False, "error": "Product not found"}), 404

    if not current_app.config.get("AI_PRODUCT_STORY_ENABLED", False):
        return (
            jsonify(
                {
                    "success": False,
                    "error": (
                        "AI story card generation is disabled. Set AI_PRODUCT_STORY_ENABLED=true "
                        "and OPENAI_API_KEY in the environment, or write the boxes by hand."
                    ),
                }
            ),
            400,
        )

    from app.services.product_story_ai import generate_story_card_draft

    draft = generate_story_card_draft(product, actor_id=current_user.id)
    if draft is None:
        return (
            jsonify(
                {
                    "success": False,
                    "error": (
                        "AI generation failed. Check the OpenAI API key and try again, "
                        "or write the story card by hand."
                    ),
                }
            ),
            502,
        )

    return jsonify(
        {
            "success": True,
            "message": "Draft generated. Review the boxes, then save to apply.",
            "data": {
                "story_what_it_is": draft.what_it_is,
                "story_who_it_is_for": draft.who_it_is_for,
                "story_materials": draft.materials,
                "story_customization_options": draft.customization_options,
                "story_internal_compliance_notes": draft.internal_compliance_notes,
            },
        }
    )


@bp.route("/studio/<int:product_id>/dead-stock/generate", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def generate_product_dead_stock(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        abort(404)
    recommendation = generate_dead_stock_recommendation(product)
    if recommendation is None:
        flash("No dead-stock rescue recommendation is needed right now.", "info")
    else:
        flash("Dead-stock rescue recommendation generated.", "success")
    return redirect(url_for("products.studio", product_id=product.id))


@bp.route("/studio/dead-stock/<int:recommendation_id>/<action>", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def update_dead_stock_recommendation(recommendation_id: int, action: str):
    recommendation = get_by_id(DeadStockRecommendation, recommendation_id)
    if recommendation is None:
        abort(404)
    notes = (request.form.get("action_notes") or "").strip() or None
    if action == "accept":
        accept_dead_stock_recommendation(recommendation, notes=notes, actor_id=current_user.id)
        flash("Dead-stock recommendation accepted.", "success")
    elif action == "dismiss":
        dismiss_dead_stock_recommendation(recommendation, notes=notes, actor_id=current_user.id)
        flash("Dead-stock recommendation dismissed.", "info")
    else:
        abort(404)
    return redirect(url_for("products.studio", product_id=recommendation.product_id))


@bp.route("/studio/<int:product_id>/retire", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def retire_studio_product(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        abort(404)
    reason = (request.form.get("reason") or "").strip()
    if not reason:
        flash("Retirement reason is required.", "danger")
        return redirect(url_for("products.studio", product_id=product.id))
    retire_product(
        product,
        reason=reason,
        discount_remaining=bool(request.form.get("discount_remaining")),
        actor_id=current_user.id,
    )
    flash("Product retired and hidden from public/POS sales.", "success")
    return redirect(url_for("products.studio", product_id=product.id))


@bp.route("/studio/<int:product_id>/delete", methods=["POST"])
@roles_required(UserRole.ADMIN)
def delete_studio_product(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        abort(404)
    confirmation = (request.form.get("confirm_slug") or "").strip()
    if confirmation != product.slug:
        flash(f'Type the product slug "{product.slug}" to confirm deletion.', "danger")
        return redirect(url_for("products.studio", product_id=product.id))
    try:
        _delete_product(product)
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("product delete failed: %s", exc)
        flash("Product deletion failed. Check related records and try again.", "danger")
        return redirect(url_for("products.studio", product_id=product.id))
    flash("Product and related product files/records were deleted.", "success")
    return redirect(url_for("products.studio"))


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
            field_obj = getattr(upload_form, field, None)
            field_label = field_obj.label.text if field_obj is not None else field
            for err in field_errors:
                errors.append(f"{field_label}: {err}")
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

    # Issue 21 — stream the upload straight to storage (chunked) and compute the
    # SHA256/size while streaming, instead of loading the whole file into memory.
    storage_ref, file_sha256, file_size = upload_stream_to_storage(
        file.stream,
        bucket=bucket,
        key=key,
        local_root=local_root,
        content_type=content_type,
    )

    # Issue 8 — split quotable (sliceable) from preview-only formats. GLB/GLTF
    # can be stored for display but cannot be analyzed for filament/time.
    from app.services.model_analysis import is_quotable_format, normalize_scale_percent

    quotable = is_quotable_format(file.filename)

    config = {
        "original_filename": file.filename,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": current_user.id,
        "printer_profile": upload_form.printer_profile.data,
        "material": upload_form.material.data,
        "filament_density": str(upload_form.filament_density.data),
        "nozzle_diameter": str(upload_form.nozzle_diameter.data),
        "layer_height": str(upload_form.layer_height.data),
        "perimeters": upload_form.perimeters.data,
        "top_solid_layers": upload_form.top_solid_layers.data,
        "bottom_solid_layers": upload_form.bottom_solid_layers.data,
        "infill_percent": upload_form.infill_percent.data,
        "infill_pattern": upload_form.infill_pattern.data,
        "supports": upload_form.supports.data,
        "brim_width": str(upload_form.brim_width.data),
        "copies": upload_form.copies.data,
        "scale_percent": normalize_scale_percent(upload_form.scale_percent.data),
        "preserve_orientation": bool(upload_form.preserve_orientation.data),
        "multicolor": bool(upload_form.multicolor.data),
        "use_embedded_settings": bool(upload_form.use_embedded_settings.data),
        "retain_gcode": bool(upload_form.retain_gcode.data),
        "convert_to_glb": bool(upload_form.convert_to_glb.data),
    }
    # Serialize the source-current flip and exact-run supersession. This lock is
    # held until the single commit below, so concurrent uploads cannot leave a
    # source asset without its corresponding current run.
    product = lock_product_for_analysis(product.id)
    if product is None:  # Product may have been removed while the file streamed.
        db.session.rollback()
        return jsonify({"success": False, "error": "Product not found"}), 404

    product.model_file_path = storage_ref
    product.model_convert_to_glb = bool(upload_form.convert_to_glb.data)
    # Issue 40 — only scalar settings may live on the product row.
    product.model_analysis_config = sanitize_analysis_config(config)
    product.analysis_error = None
    product.analysis_completed_at = None
    product.convert_status = None
    product.conversion_error = None
    product.converted_model_path = None
    product.gcode_path = None

    # Issue 6/7 — record the upload as a current source-model asset.
    asset = create_model_asset(
        product,
        storage_reference=storage_ref,
        original_filename=file.filename,
        safe_filename=safe_filename,
        content_type=content_type,
        size_bytes=file_size,
        sha256=file_sha256,
        asset_kind=AssetKind.SOURCE_MODEL,
    )

    from app.services.model_asset_metadata import write_model_metadata

    # Issue 21 — pass the already-computed hash/size so metadata needn't re-read.
    write_model_metadata(product, sha256=file_sha256, size_bytes=file_size)

    if not quotable:
        # Preview-only format: stored for reference, but no analysis is attempted.
        product.analysis_status = None
        product.analysis_error = None
        db.session.commit()
        get_audit_client().record(
            action="product_model.uploaded",
            entity_type="product",
            entity_id=str(product.id),
            actor_id=str(current_user.id),
            actor_type="user",
            actor_display_name=getattr(current_user, "display_name", None),
            source_module="products.studio_routes",
            tenant_id=str(product.business_id) if product.business_id else None,
            after_state={"model_file_path": storage_ref, "quotable": False},
            metadata={"filename": file.filename, "preview_only": True},
        )
        return jsonify(
            {
                "success": True,
                "product_id": product.id,
                "task_id": None,
                "file_location": storage_ref,
                "preview_only": True,
                "message": (
                    "This format is stored for preview/reference only and cannot be "
                    "analyzed for filament usage or print time."
                ),
            }
        )

    # Issue 6 — create the exact race-proof run before enqueueing. Its identity
    # and immutable source/settings snapshot travel with the Celery message.
    product.analysis_status = "pending"
    product.analysis_requested_at = datetime.now(timezone.utc)
    run = start_analysis_run(
        product,
        source_asset=asset,
        requested_by_id=current_user.id,
        settings=config,
        product_locked=True,
    )
    db.session.commit()

    get_audit_client().record(
        action="product_model.uploaded",
        entity_type="product",
        entity_id=str(product.id),
        actor_id=str(current_user.id),
        actor_type="user",
        actor_display_name=getattr(current_user, "display_name", None),
        source_module="products.studio_routes",
        tenant_id=str(product.business_id) if product.business_id else None,
        after_state={"model_file_path": storage_ref, "quotable": True},
        metadata={
            "filename": file.filename,
            "convert_to_glb": product.model_convert_to_glb,
            "printer_profile": product.model_analysis_config.get("printer_profile"),
        },
    )
    get_audit_client().record(
        action="model_analysis.queued",
        entity_type="product",
        entity_id=str(product.id),
        actor_id=str(current_user.id),
        actor_type="user",
        actor_display_name=getattr(current_user, "display_name", None),
        source_module="products.studio_routes",
        tenant_id=str(product.business_id) if product.business_id else None,
        metadata={"percent": 2, "message": "Model analysis queued"},
    )

    # Issue 4 — a real broker health check; .delay() is never "silently fine".
    celery = _get_celery()
    task_id = None
    enqueue_ok = False
    if celery is not None:
        try:
            from app.services.runtime_checks import is_celery_healthy

            if is_celery_healthy():
                from app.tasks.model_analysis import analyze_product_model

                task = analyze_product_model.delay(product.id, run.id)
                task_id = task.id
                enqueue_ok = True
        except Exception as exc:  # broker down / import error / queue rejection
            current_app.logger.warning("model analysis enqueue failed: %s", exc)
            enqueue_ok = False

    if not enqueue_ok:
        product.analysis_status = "failed"
        product.analysis_error = (
            "Background worker is not running. Please contact an administrator or try again later."
        )
        db.session.commit()
        get_audit_client().record(
            action="model_analysis.enqueue_failed",
            entity_type="product",
            entity_id=str(product.id),
            actor_id=str(current_user.id),
            actor_type="user",
            actor_display_name=getattr(current_user, "display_name", None),
            source_module="products.studio_routes",
            tenant_id=str(product.business_id) if product.business_id else None,
            metadata={"error": "worker unavailable", "file_location": storage_ref},
        )
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Worker unavailable — the model was saved but analysis could not be queued.",
                    "file_location": storage_ref,
                }
            ),
            503,
        )

    return jsonify(
        {
            "success": True,
            "product_id": product.id,
            "task_id": task_id,
            "file_location": storage_ref,
        }
    )


@bp.route("/studio/<int:product_id>/assets")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def product_assets(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        abort(404)
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    assets = list_product_assets(product.id, bucket=bucket, local_root=local_root)
    metadata = {}
    if product.model_metadata_path:
        from app.services.model_asset_metadata import read_model_metadata

        metadata = read_model_metadata(product)
    assets_by_name = {asset["name"]: asset for asset in assets}
    for asset in assets:
        asset["kind"] = _asset_kind(asset["name"])
        sidecar_name = f"{Path(asset['name']).stem}.metadata.json"
        sidecar = assets_by_name.get(sidecar_name)
        asset_metadata = {}
        if sidecar and asset["kind"] != "metadata":
            try:
                asset_metadata = json.loads(download_storage_bytes(sidecar["reference"]))
            except OSError, ValueError, TypeError:
                asset_metadata = {}
        elif asset["reference"] in {
            product.model_file_path,
            product.converted_model_path,
            product.gcode_path,
        }:
            asset_metadata = metadata
        asset["metadata"] = asset_metadata
        asset["is_pmp_compatible"] = Path(asset["name"]).suffix.lower() in {".stl", ".3mf"}
        asset["is_packed_plate"] = (
            "__packed-plate__" in asset["name"]
            or asset_metadata.get("schema") == "dfpos.pmp-packed-plate"
        )
        asset["download_url"] = url_for(
            "products.download_product_asset", product_id=product.id, filename=asset["name"]
        )
        asset["delete_url"] = url_for(
            "products.delete_product_asset", product_id=product.id, filename=asset["name"]
        )
        asset["pmp_url"] = url_for(
            "products.pack_product_asset", product_id=product.id, filename=asset["name"]
        )
        asset["metadata_will_delete"] = bool(sidecar) or asset["reference"] in {
            product.model_file_path,
            product.converted_model_path,
            product.gcode_path,
        }
    return jsonify({"success": True, "product_id": product.id, "assets": assets})


@bp.route("/studio/<int:product_id>/assets/<path:filename>/pmp", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def pack_product_asset(product_id: int, filename: str):
    product = get_by_id(Product, product_id)
    if product is None or Path(filename).name != filename:
        abort(404)
    if Path(filename).suffix.lower() not in {".stl", ".3mf"}:
        return jsonify({"success": False, "error": "PMP supports STL and 3MF assets only"}), 400
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    assets = list_product_assets(product.id, bucket=bucket, local_root=local_root)
    asset = next((item for item in assets if item["name"] == filename), None)
    if asset is None:
        return jsonify({"success": False, "error": "Asset not found"}), 404

    from app.tasks.model_analysis import pack_product_model

    task = pack_product_model.delay(product.id, asset["reference"], filename, current_user.id)
    get_audit_client().record(
        action="product_model.pmp.queued",
        entity_type="product",
        entity_id=str(product.id),
        actor_id=str(current_user.id),
        actor_type="user",
        actor_display_name=getattr(current_user, "display_name", None),
        source_module="products.studio_routes",
        tenant_id=str(product.business_id) if product.business_id else None,
        metadata={"filename": filename, "task_id": task.id, "percent": 2},
    )
    return jsonify({"success": True, "task_id": task.id, "filename": filename})


def _asset_kind(filename: str) -> str:
    name = filename.lower()
    if name.endswith(".metadata.json"):
        return "metadata"
    if name.endswith(".gcode.3mf"):
        return "gcode"
    extension = Path(name).suffix
    if extension in {".stl", ".3mf", ".obj", ".gltf"}:
        return "model"
    if extension == ".glb":
        return "preview"
    if extension in {".gcode", ".bgcode"}:
        return "gcode"
    if extension in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return "image"
    return "file"


@bp.route("/studio/<int:product_id>/assets/<path:filename>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def download_product_asset(product_id: int, filename: str):
    product = get_by_id(Product, product_id)
    safe_name = normalize_product_asset_name(product_id, filename)
    if product is None or safe_name is None:
        abort(404)
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    assets = list_product_assets(product.id, bucket=bucket, local_root=local_root)
    asset = next((item for item in assets if item["name"] == safe_name), None)
    if asset is None:
        abort(404)
    return send_storage_reference(
        asset["reference"],
        download_name=safe_name,
        as_attachment=True,
    )


@bp.route("/studio/<int:product_id>/assets/<path:filename>", methods=["DELETE"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def delete_product_asset(product_id: int, filename: str):
    product = get_by_id(Product, product_id)
    safe_name = normalize_product_asset_name(product_id, filename)
    if product is None or safe_name is None:
        abort(404)

    if is_analysis_run_asset_name(safe_name):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Analysis-run artifacts are retained with their run history and cannot be deleted.",
                }
            ),
            409,
        )

    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    assets = list_product_assets(product.id, bucket=bucket, local_root=local_root)
    asset = next((item for item in assets if item["name"] == safe_name), None)
    if asset is None:
        return jsonify({"success": False, "error": "Asset not found"}), 404

    reference = asset["reference"]
    kind = _asset_kind(safe_name)
    deleted_references = [reference]
    delete_storage_reference(reference)

    metadata_deleted = kind == "metadata"
    asset_path = PurePosixPath(safe_name)
    sidecar_name = (asset_path.parent / f"{asset_path.stem}.metadata.json").as_posix()
    sidecar = next((item for item in assets if item["name"] == sidecar_name), None)
    if kind in {"model", "preview", "gcode"} and sidecar and sidecar["reference"] != reference:
        delete_storage_reference(sidecar["reference"])
        deleted_references.append(sidecar["reference"])
        metadata_deleted = True
        if product.model_metadata_path == sidecar["reference"]:
            product.model_metadata_path = None
    elif (
        kind in {"model", "preview", "gcode"}
        and reference in {product.model_file_path, product.converted_model_path, product.gcode_path}
        and product.model_metadata_path
        and product.model_metadata_path != reference
    ):
        delete_storage_reference(product.model_metadata_path)
        deleted_references.append(product.model_metadata_path)
        product.model_metadata_path = None
        metadata_deleted = True

    if product.model_file_path == reference:
        product.model_file_path = None
        product.analysis_status = None
        product.analysis_error = None
        product.analysis_completed_at = None
        product.model_analysis_config = None
    if product.converted_model_path == reference:
        product.converted_model_path = None
        product.convert_status = None
        product.conversion_error = None
    if product.gcode_path == reference:
        product.gcode_path = None
    if product.model_metadata_path == reference:
        product.model_metadata_path = None

    image = next((item for item in product.images if item.file_path == reference), None)
    if image is not None:
        if product.default_image_path == reference:
            product.default_image_path = None
        if product.pos_image_path == reference:
            product.pos_image_path = None
        db.session.delete(image)

    db.session.commit()
    get_audit_client().record(
        action="product_asset.deleted",
        entity_type="product",
        entity_id=str(product.id),
        actor_id=str(current_user.id),
        actor_type="user",
        actor_display_name=getattr(current_user, "display_name", None),
        source_module="products.studio_routes",
        tenant_id=str(product.business_id) if product.business_id else None,
        before_state={"references": deleted_references},
        after_state={},
        metadata={"filename": safe_name, "kind": kind, "metadata_deleted": metadata_deleted},
    )
    return jsonify({"success": True, "deleted": safe_name, "metadata_deleted": metadata_deleted})


@bp.route("/studio/<int:product_id>/calculate-costs", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def calculate_product_costs(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        return (
            jsonify(
                {"success": False, "status": "failed", "data": None, "error": "Product not found"}
            ),
            404,
        )

    # Issue 16 — a "successful" cost with no model data still renders normal
    # cost cards and misleads the user. Block automatic calculation until the
    # model has been analyzed, unless the user explicitly confirms they want an
    # estimate without a model.
    model_ready = bool(
        product.analysis_status == "complete"
        and product.parsed_filament_grams is not None
        and product.parsed_print_minutes is not None
    )
    confirm_no_model = request.form.get("confirm_no_model") or (
        request.get_json(silent=True) or {}
    ).get("confirm_no_model")
    if not model_ready and not confirm_no_model:
        return (
            jsonify(
                {
                    "success": False,
                    "status": "no_model",
                    "data": None,
                    "error": (
                        "No model analysis is available. Material and machine costs "
                        "cannot be calculated without a model. Confirm to estimate anyway."
                    ),
                    "confidence": "none",
                    "warning": "No model data — material and machine costs reflect estimates only.",
                }
            ),
            409,
        )

    # Issue 17 — capture the prior current snapshot for the audit before_state
    # before persist_cost_snapshot marks it stale.
    prior_snapshot = (
        db.session.query(CostSnapshot)
        .filter(CostSnapshot.product_id == product.id, CostSnapshot.stale.is_(False))
        .order_by(CostSnapshot.created_at.desc())
        .first()
    )

    celery = _get_celery()
    if celery is not None and model_ready:
        from app.tasks.cost_calculation import calculate_product_cost_task

        task = calculate_product_cost_task.delay(product_id, actor_id=current_user.id)
        return jsonify(
            {"success": True, "status": "queued", "data": {"task_id": task.id}, "error": ""}
        )

    breakdown = calculate_product_cost(product=product)
    product.estimated_material_cost = breakdown.material_cost
    product.estimated_profit = breakdown.margin_dollars
    product.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
    persist_cost_snapshot(
        product=product,
        breakdown=breakdown,
        snapshot_reason="studio.product",
        actor_id=current_user.id,
        before_snapshot_id=prior_snapshot.id if prior_snapshot else None,
    )
    db.session.commit()
    return jsonify(
        {
            "success": True,
            "status": "complete",
            "data": {
                "total_cost": str(breakdown.total_cost),
                "suggested_price": str(breakdown.suggested_price),
                "margin_percent": str(breakdown.margin_percent),
                "margin_dollars": str(breakdown.margin_dollars),
                "material_cost": str(breakdown.material_cost),
                "filament_grams": str(breakdown.filament_grams),
                "print_minutes": str(breakdown.print_minutes),
                "confidence": breakdown.confidence,
                "evidence_source": breakdown.evidence_source,
                "snapshot_id": breakdown.snapshot_id,
                "model_ready": model_ready,
                "warning": (
                    None
                    if model_ready
                    else "No model data — material and machine costs reflect estimates only."
                ),
            },
            "error": "",
        }
    )


@bp.route("/studio/<int:product_id>/preview-costs", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def preview_product_costs(product_id: int):
    product = get_by_id(Product, product_id)
    if product is None:
        return jsonify({"success": False, "error": "Product not found"}), 404

    data = request.get_json(silent=True) or request.form.to_dict()
    try:
        sale_price = _decimal_from_payload(data, "base_price")
        packaging_cost = _decimal_from_payload(data, "packaging_cost_override")
        target_margin_percent = _decimal_from_payload(data, "target_margin_percent_override")
        market_allocation = _decimal_from_payload(data, "market_allocation_override")
        payment_fee_rate = _decimal_from_payload(data, "payment_fee_rate_override")
        product.estimated_labor_minutes = _int_from_payload(data, "estimated_labor_minutes") or 0
        product.material_spool_override = _int_from_payload(data, "material_spool_override")
        breakdown = calculate_product_cost(
            product=product,
            sale_price=sale_price,
            packaging_cost=packaging_cost,
            target_margin_percent=target_margin_percent,
            market_allocation=market_allocation,
            payment_fee_rate=payment_fee_rate,
        )
    except (ArithmeticError, TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Unable to preview costs: {exc}"}), 400

    db.session.rollback()
    return jsonify(
        {
            "success": True,
            "status": "complete",
            "data": _cost_preview_payload(
                breakdown,
                sale_price=sale_price
                if sale_price is not None
                else Decimal(str(product.base_price or 0)),
            ),
        }
    )


@bp.route("/studio/task-status/<task_id>")
@roles_required(UserRole.ADMIN, UserRole.STAFF)
def task_status(task_id: str):
    # Issues 5/36/19 — every status response uses one envelope:
    #   {"success": bool, "status": str, "data": {...}|null, "error": str}
    # A Celery task that finished but returned {success: false} (e.g. a failed
    # analysis that did not raise) must NOT read as "complete" — the envelope's
    # `success` field is authoritative, not the Celery state.
    celery = _get_celery()
    if celery is None:
        return jsonify({"success": True, "status": "complete", "data": None, "error": ""})

    result = celery.AsyncResult(task_id)
    state = result.state

    if state == "SUCCESS":
        payload = result.result
        # Tasks return a task_envelope {success, data, error}; unwrap it so the
        # browser never has to handle two shapes.
        if isinstance(payload, dict) and "success" in payload:
            success = bool(payload.get("success"))
            return jsonify(
                {
                    "success": success,
                    "status": "failed" if not success else "complete",
                    "data": payload.get("data"),
                    "error": payload.get("error") or "",
                }
            )
        return jsonify({"success": True, "status": "complete", "data": payload, "error": ""})

    if state == "FAILURE":
        error = str(result.info) if result.info else "Task failed"
        return jsonify({"success": False, "status": "failed", "data": None, "error": error})

    info = result.info if isinstance(result.info, dict) else None
    if state == "PENDING":
        status = "queued"
    elif state in ("STARTED", "RETRY"):
        status = "started"
    elif state == "PROGRESS":
        # The task may report a sub-status (validating/slicing/storing_gcode/
        # costing/converting) inside its progress info (Issue 19).
        status = (info or {}).get("status", "started")
    else:
        status = state.lower()

    return jsonify(
        {
            "success": True,
            "status": status,
            "data": info,
            "error": "",
        }
    )


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
    product = lock_product_for_analysis(product_id)
    if product is None:
        return jsonify({"success": False, "error": "Product not found"}), 404

    # Issue 50 — don't queue a duplicate analysis while one is already running.
    if is_analysis_in_progress(product):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "An analysis is already in progress for this product.",
                }
            ),
            409,
        )

    # Issue 27 — clear stale cost/analysis fields so the UI can't show old numbers
    # as if they were current while the new run is in flight.
    reset_product_analysis(product)
    source_asset = current_asset(product, AssetKind.SOURCE_MODEL)
    if source_asset is None:
        db.session.rollback()
        return jsonify({"success": False, "error": "No source model is available."}), 409
    run = start_analysis_run(
        product,
        source_asset=source_asset,
        requested_by_id=current_user.id,
        settings=dict(product.model_analysis_config or {}),
        product_locked=True,
    )
    db.session.commit()

    celery = _get_celery()
    task_id = None
    if celery is not None:
        from app.tasks.model_analysis import analyze_product_model

        task = analyze_product_model.delay(product.id, run.id)
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
            "surface_area_mm2": (
                float(product.parsed_surface_area_mm2) if product.parsed_surface_area_mm2 else None
            ),
            "triangle_count": product.parsed_triangle_count,
            "filament_grams": (
                float(product.parsed_filament_grams) if product.parsed_filament_grams else None
            ),
            "print_minutes": (
                float(product.parsed_print_minutes) if product.parsed_print_minutes else None
            ),
            "material_cost": (
                str(product.parsed_material_cost) if product.parsed_material_cost else None
            ),
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

    photo_shot = None
    photo_shot_id = (request.form.get("photo_shot_id") or "").strip()
    if photo_shot_id:
        if not photo_shot_id.isdigit():
            return jsonify({"success": False, "error": "Invalid photo shot"}), 400
        photo_shot = ProductPhotoShot.query.filter_by(
            id=int(photo_shot_id), product_id=product.id
        ).first()
        if photo_shot is None:
            return jsonify({"success": False, "error": "Photo shot not found"}), 404

    file = request.files.get("image")
    if not file:
        return jsonify({"success": False, "error": "No image file provided"}), 400

    # Issue 22 — extension allow-list (no .gif).
    from app.services.image_validation import (
        ALLOWED_IMAGE_EXTENSIONS,
        validate_image_file,
    )

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return (
            jsonify({"success": False, "error": "Unsupported image type. Use JPG, PNG, or WebP."}),
            400,
        )

    max_bytes = current_app.config.get("PRODUCT_IMAGE_MAX_BYTES", 5 * 1024 * 1024)

    safe_filename = _preferred_image_filename(product, file.filename or f"image{ext}")
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
    key = image_storage_key(product.id, safe_filename)
    content_type = content_type_for_name(file.filename, "image/jpeg")

    # Issue 34 — stream the image to storage (chunked) instead of file.read()
    # loading the whole file into memory; hash/size are computed while streaming.
    storage_ref, file_sha256, file_size = upload_stream_to_storage(
        file.stream,
        bucket=bucket,
        key=key,
        local_root=local_root,
        content_type=content_type,
    )

    # Enforce the per-image size cap. If oversize, remove the stored object and
    # reject before any DB row is created.
    if file_size > max_bytes:
        delete_storage_reference(storage_ref)
        limit_mb = max_bytes // (1024 * 1024)
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Image too large. The maximum product image size is {limit_mb} MB.",
                }
            ),
            413,
        )

    # Issue 22 — validate the real content with Pillow (magic bytes), not just
    # the filename. For S3 references, materialize to a temp file first.
    if is_s3_reference(storage_ref):
        tmp_path, cleanup = materialize_storage_reference(storage_ref, suffix=ext)
        image_error, detected_mime = validate_image_file(tmp_path)
        if cleanup:
            Path(tmp_path).unlink(missing_ok=True)
    else:
        image_error, detected_mime = validate_image_file(storage_ref)

    if image_error:
        delete_storage_reference(storage_ref)
        return jsonify({"success": False, "error": image_error}), 400

    if detected_mime:
        content_type = detected_mime

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

    if photo_shot is not None:
        photo_shot = update_photo_shot(
            photo_shot,
            completed=True,
            image_reference=storage_ref,
            notes=photo_shot.notes,
            actor_id=current_user.id,
        )

    # Issue 22 — audit the upload.
    get_audit_client().record(
        action="product_image.uploaded",
        entity_type="product",
        entity_id=str(product.id),
        actor_id=str(current_user.id),
        actor_type="user",
        actor_display_name=getattr(current_user, "display_name", None),
        source_module="products.studio_routes",
        tenant_id=str(product.business_id) if product.business_id else None,
        after_state={
            "image_id": img.id,
            "file_path": storage_ref,
            "is_default": img.is_default,
            "is_pos": img.is_pos,
            "content_type": content_type,
            "size_bytes": file_size,
            "sha256": file_sha256,
            "photo_shot_id": photo_shot.id if photo_shot else None,
        },
        metadata={"filename": file.filename, "alt_text": img.alt_text},
    )

    return jsonify(
        {
            "success": True,
            "image_id": img.id,
            "file_path": storage_ref,
            "is_default": img.is_default,
            "is_pos": img.is_pos,
            "url": url_for("products.serve_product_image", image_id=img.id),
            "shot": (
                {
                    "id": photo_shot.id,
                    "completed": photo_shot.completed,
                    "image_reference": photo_shot.image_reference,
                    "label": photo_shot.label,
                }
                if photo_shot
                else None
            ),
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
    _audit_image_action(img, "product_image.set_default")
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
    _audit_image_action(img, "product_image.set_pos")
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

    _audit_image_action(img, "product_image.deleted")
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

    try:
        from app.services.ai.trend_scout.analyzer.trend_detector import (
            _catalog_metrics,
            OpportunityCandidate,
            _score_candidate,
            compute_velocity_and_momentum,
        )
        from app.services.trend_match import match_product_to_term

        products = db.session.query(Product).filter(Product.deleted_at.is_(None)).all()
        catalog_metrics = _catalog_metrics(db.session)
        _ = compute_velocity_and_momentum(db.session, lookback_weeks=8)
    except Exception as e:
        current_app.logger.error(
            "Trend score catalog/metrics failed for product %s: %s", product_id, e, exc_info=True
        )
        return jsonify({"success": False, "error": f"Catalog/metrics calculation failed: {e}"}), 500

    product_metrics = catalog_metrics.get(product.id, {})
    units_sold = int(product_metrics.get("units_sold", 0))
    revenue = float(product_metrics.get("revenue", 0))

    try:
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
            estimated_print_minutes=float(
                product.parsed_print_minutes or product.estimated_print_minutes or 0
            ),
            license_status=(
                product.license_status.value
                if hasattr(product.license_status, "value")
                else str(product.license_status)
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
    except Exception as e:
        current_app.logger.error(
            "Trend score candidate/scoring failed for product %s: %s", product_id, e, exc_info=True
        )
        return jsonify({"success": False, "error": f"Scoring failed: {e}"}), 500

    try:
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
    except Exception as e:
        current_app.logger.warning("Trend score audit failed (non-fatal): %s", e)

    return jsonify(
        {
            "success": True,
            "product_id": product.id,
            "product_name": product.name,
            "score": scored,
        }
    )
