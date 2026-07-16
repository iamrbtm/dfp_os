from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models import (
    DeadStockRecommendation,
    DeadStockRecommendationStatus,
    InventoryRecord,
    LicenseStatus,
    OrderItem,
    Product,
    ProductLaunchChecklistItem,
    ProductLaunchChecklistKey,
    ProductPhotoShot,
    ProductPhotoShotType,
    ProductStatus,
)
from app.services.admin_mutations import snapshot_instance
from app.services.audit import record_audit_event


LAUNCH_CHECKLIST_LABELS = {
    ProductLaunchChecklistKey.LICENSE_VERIFIED: "License verified",
    ProductLaunchChecklistKey.MODEL_ANALYZED: "Model analyzed",
    ProductLaunchChecklistKey.COST_SNAPSHOT: "Cost snapshot",
    ProductLaunchChecklistKey.PRODUCT_PHOTOS: "Product photos",
    ProductLaunchChecklistKey.POS_TILE: "POS tile",
    ProductLaunchChecklistKey.PUBLIC_DESCRIPTION: "Public description",
    ProductLaunchChecklistKey.INVENTORY_TARGET: "Inventory target",
    ProductLaunchChecklistKey.MARKET_TEST_PLAN: "Market test plan",
    ProductLaunchChecklistKey.SAFETY_CARE_NOTES: "Safety and care notes",
}

PHOTO_SHOT_LABELS = {
    ProductPhotoShotType.HERO: "Hero",
    ProductPhotoShotType.SCALE_IN_HAND: "Scale in hand",
    ProductPhotoShotType.COLOR_VARIANTS: "Color variants",
    ProductPhotoShotType.CLOSE_UP: "Close-up",
    ProductPhotoShotType.PACKAGING: "Packaging",
    ProductPhotoShotType.BOOTH_DISPLAY: "Booth display",
    ProductPhotoShotType.POS_TILE: "POS tile",
}


@dataclass(frozen=True)
class ReadinessResult:
    score: int
    breakdown: list[dict[str, object]]
    critical_blockers: list[str]


def ensure_product_ops_defaults(product: Product) -> None:
    existing_checklist = {item.key for item in product.launch_checklist_items}
    for key, label in LAUNCH_CHECKLIST_LABELS.items():
        if key not in existing_checklist:
            db.session.add(ProductLaunchChecklistItem(product=product, key=key, label=label))

    existing_shots = {item.shot_type for item in product.photo_shots}
    for shot_type, label in PHOTO_SHOT_LABELS.items():
        if shot_type not in existing_shots:
            db.session.add(ProductPhotoShot(product=product, shot_type=shot_type, label=label))
    db.session.flush()


def calculate_product_readiness(product: Product) -> ReadinessResult:
    ensure_product_ops_defaults(product)
    breakdown: list[dict[str, object]] = []
    blockers: list[str] = []

    def add(label: str, points: int, passed: bool, reason: str, critical: bool = False):
        earned = points if passed else 0
        breakdown.append({"label": label, "points": points, "earned": earned, "passed": passed, "reason": reason})
        if critical and not passed:
            blockers.append(reason)

    license_ok = product.license_status in {
        LicenseStatus.COMMERCIAL_ALLOWED,
        LicenseStatus.COMMERCIAL_SUBSCRIPTION,
        LicenseStatus.CUSTOMER_OWNED,
    } or bool(product.model_commercial_use_allowed)
    add("License", 20, license_ok, "Commercial rights need review.", critical=True)
    add("Model analysis", 12, product.analysis_status == "complete" or bool(product.gcode_path), "Model analysis is missing.")
    add("Cost data", 12, bool(product.cost_snapshots) or (product.estimated_material_cost or 0) > 0, "Cost snapshot or material cost is missing.")
    completed_shots = sum(1 for shot in product.photo_shots if shot.completed)
    has_photo_record = bool(product.images) or bool(product.default_image_path)
    add(
        "Photos",
        12,
        has_photo_record or completed_shots >= 2,
        "Product photos or shot-list completion are missing.",
    )
    add("Public copy", 12, bool(product.description and product.short_description), "Public description is incomplete.")
    add("Price", 10, Decimal(str(product.base_price or 0)) > 0, "Base price is missing.", critical=True)
    add("POS/public visibility", 8, bool(product.is_pos_visible or product.is_public), "Product is hidden from both POS and public catalog.")
    add("Safety/care", 7, bool(product.safety_notes and product.care_instructions), "Safety or care notes are missing.")
    add("Inventory", 7, _inventory_on_hand(product) > 0, "No finished goods inventory is available.")

    score = sum(int(item["earned"]) for item in breakdown)
    if product.license_status in {LicenseStatus.PERSONAL_ONLY, LicenseStatus.RESTRICTED, LicenseStatus.NEEDS_REVIEW}:
        score = min(score, 45)
    return ReadinessResult(score=min(score, 100), breakdown=breakdown, critical_blockers=blockers)


def sync_launch_checklist(product: Product) -> list[ProductLaunchChecklistItem]:
    ensure_product_ops_defaults(product)
    readiness = calculate_product_readiness(product)
    completed_shots = sum(1 for shot in product.photo_shots if shot.completed)
    status_by_key = {
        ProductLaunchChecklistKey.LICENSE_VERIFIED: not any("Commercial rights" in b for b in readiness.critical_blockers),
        ProductLaunchChecklistKey.MODEL_ANALYZED: product.analysis_status == "complete" or bool(product.gcode_path),
        ProductLaunchChecklistKey.COST_SNAPSHOT: bool(product.cost_snapshots) or (product.estimated_material_cost or 0) > 0,
        ProductLaunchChecklistKey.PRODUCT_PHOTOS: bool(product.images) or bool(product.default_image_path) or completed_shots >= 2,
        ProductLaunchChecklistKey.POS_TILE: bool(product.pos_image_path or product.is_pos_visible),
        ProductLaunchChecklistKey.PUBLIC_DESCRIPTION: bool(product.description and product.short_description),
        ProductLaunchChecklistKey.INVENTORY_TARGET: _inventory_on_hand(product) > 0,
        ProductLaunchChecklistKey.MARKET_TEST_PLAN: bool(product.tags),
        ProductLaunchChecklistKey.SAFETY_CARE_NOTES: bool(product.safety_notes and product.care_instructions),
    }
    for item in product.launch_checklist_items:
        if item.override_reason:
            item.completed = True
        else:
            item.completed = bool(status_by_key.get(item.key, False))
    return list(product.launch_checklist_items)


def update_checklist_item(item: ProductLaunchChecklistItem, *, completed: bool, notes: str | None, override_reason: str | None, actor_id: int | None = None) -> ProductLaunchChecklistItem:
    before_state = snapshot_instance(item)
    item.completed = completed
    item.notes = notes
    item.override_reason = override_reason
    db.session.add(item)
    db.session.commit()
    _audit("product_launch_checklist.updated", "product_launch_checklist_item", item.id, before_state, snapshot_instance(item), actor_id)
    return item


def update_photo_shot(shot: ProductPhotoShot, *, completed: bool, image_reference: str | None, notes: str | None, actor_id: int | None = None) -> ProductPhotoShot:
    before_state = snapshot_instance(shot)
    shot.completed = completed
    shot.image_reference = image_reference
    shot.notes = notes
    db.session.add(shot)
    db.session.commit()
    _audit("product_photo_shot.updated", "product_photo_shot", shot.id, before_state, snapshot_instance(shot), actor_id)
    return shot


def update_story_card(product: Product, data: dict[str, str | None], *, actor_id: int | None = None) -> Product:
    before_state = snapshot_instance(product)
    product.story_what_it_is = data.get("story_what_it_is")
    product.story_who_it_is_for = data.get("story_who_it_is_for")
    product.story_materials = data.get("story_materials")
    product.story_customization_options = data.get("story_customization_options")
    product.story_internal_compliance_notes = data.get("story_internal_compliance_notes")
    db.session.add(product)
    db.session.commit()
    _audit("product_story_card.updated", "product", product.id, before_state, snapshot_instance(product), actor_id)
    return product


def generate_dead_stock_recommendation(product: Product) -> DeadStockRecommendation | None:
    quantity = _inventory_on_hand(product)
    if quantity <= 0:
        return None
    sold = db.session.query(func.coalesce(func.sum(OrderItem.quantity), 0)).filter(OrderItem.product_id == product.id).scalar() or 0
    margin = Decimal(str(product.estimated_profit or 0))
    score = 0
    reasons = []
    if sold == 0 and quantity >= 3:
        score += 45
        reasons.append("inventory has not sold yet")
    if quantity >= 10:
        score += 20
        reasons.append("quantity on hand is high")
    if margin <= 0:
        score += 20
        reasons.append("margin is missing or low")
    if not product.is_public and not product.is_pos_visible:
        score += 10
        reasons.append("product is hidden from sales channels")
    if score < 35:
        return None
    action = "bundle" if margin > 0 else "retire"
    recommendation = DeadStockRecommendation(
        product=product,
        score=min(score, 100),
        suggested_action=action,
        reason=", ".join(reasons),
    )
    db.session.add(recommendation)
    db.session.commit()
    return recommendation


def accept_dead_stock_recommendation(recommendation: DeadStockRecommendation, *, notes: str | None = None, actor_id: int | None = None) -> DeadStockRecommendation:
    before_state = snapshot_instance(recommendation)
    recommendation.status = DeadStockRecommendationStatus.ACCEPTED
    recommendation.action_notes = notes
    db.session.add(recommendation)
    db.session.commit()
    _audit("dead_stock_recommendation.accepted", "dead_stock_recommendation", recommendation.id, before_state, snapshot_instance(recommendation), actor_id)
    return recommendation


def dismiss_dead_stock_recommendation(recommendation: DeadStockRecommendation, *, notes: str | None = None, actor_id: int | None = None) -> DeadStockRecommendation:
    before_state = snapshot_instance(recommendation)
    recommendation.status = DeadStockRecommendationStatus.DISMISSED
    recommendation.action_notes = notes
    db.session.add(recommendation)
    db.session.commit()
    _audit("dead_stock_recommendation.dismissed", "dead_stock_recommendation", recommendation.id, before_state, snapshot_instance(recommendation), actor_id)
    return recommendation


def retire_product(product: Product, *, reason: str, actor_id: int | None = None, discount_remaining: bool = False) -> Product:
    before_state = snapshot_instance(product)
    product.status = ProductStatus.RETIRED
    product.is_public = False
    product.is_pos_visible = False
    product.is_featured = False
    product.block_reprint = True
    product.retired_at = datetime.now(timezone.utc)
    product.retirement_reason = reason
    if discount_remaining:
        product.tags = f"{product.tags or ''},retirement-discount".strip(",")
    db.session.add(product)
    db.session.commit()
    _audit("product.retired", "product", product.id, before_state, snapshot_instance(product), actor_id)
    return product


def launch_gate(product: Product) -> tuple[bool, list[str]]:
    readiness = calculate_product_readiness(product)
    if product.launch_override_reason:
        return True, []
    if readiness.critical_blockers:
        return False, readiness.critical_blockers
    return readiness.score >= 70, [item["reason"] for item in readiness.breakdown if not item["passed"]]


def _inventory_on_hand(product: Product) -> int:
    return sum(record.quantity_on_hand for record in product.inventory_records)


def _audit(action: str, entity_type: str, entity_id: int, before_state: dict | None, after_state: dict | None, actor_id: int | None) -> None:
    record_audit_event(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        source_module=__name__,
        actor_id=actor_id,
    )
