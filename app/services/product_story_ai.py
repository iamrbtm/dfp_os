from __future__ import annotations

import json
from dataclasses import dataclass

from flask import current_app

from app.models import LicenseStatus, Product
from app.services.ai_gateway import ai_provider_configured, get_openai_compatible_client, model_for
from app.services.audit import record_audit_event

_AT_RISK_LICENSE_STATUSES = {
    LicenseStatus.UNKNOWN.value,
    LicenseStatus.PERSONAL_ONLY.value,
    LicenseStatus.RESTRICTED.value,
    LicenseStatus.NEEDS_REVIEW.value,
}

_SYSTEM_PROMPT = (
    "You write product copy for Dude Fish Printing, a family-run 3D printing business. "
    "You are filling a Product Story Card used on the public shop pages and internal records. "
    "Write friendly, plain-language copy in 1-3 short sentences per field. "
    "Do NOT invent fake reviews, testimonials, customer counts, policies, or unsupported claims. "
    "Do not claim durability, safety, or toy suitability beyond what the provided data supports. "
    "Never invent a license or compliance fact — base the compliance note strictly on the "
    "license fields provided and flag anything that needs human review. "
    "Respond ONLY with a JSON object using exactly these keys: "
    '"what_it_is", "who_it_is_for", "materials", "customization_options", '
    '"internal_compliance_notes". Omit or use empty string for fields you cannot answer.'
)


@dataclass(frozen=True)
class StoryCardDraft:
    what_it_is: str | None
    who_it_is_for: str | None
    materials: str | None
    customization_options: str | None
    internal_compliance_notes: str | None
    model: str | None = None


def story_card_ai_enabled() -> bool:
    return (
        bool(current_app.config.get("AI_PRODUCT_STORY_ENABLED", False)) and ai_provider_configured()
    )


def generate_story_card_draft(
    product: Product, *, actor_id: int | None = None
) -> StoryCardDraft | None:
    """Generate a reviewable draft for all five story card boxes.

    AI output is a draft/suggestion only. It is never written to the product
    row here; the caller must present it for review and persist it through the
    existing ``update_story_card`` flow. Returns None when AI is disabled or
    generation fails so manual entry always works.
    """
    if not story_card_ai_enabled():
        return None
    try:
        draft = _generate_with_openai(product)
    except Exception as exc:
        current_app.logger.warning("AI product story card generation failed: %s", exc)
        return None
    if draft is None:
        return None
    record_audit_event(
        action="product_story_card.ai_generated",
        entity_type="product",
        entity_id=product.id,
        after_state={
            "story_what_it_is": draft.what_it_is,
            "story_who_it_is_for": draft.who_it_is_for,
            "story_materials": draft.materials,
            "story_customization_options": draft.customization_options,
            "story_internal_compliance_notes": draft.internal_compliance_notes,
        },
        metadata={"model": draft.model, "ai_assisted": True, "draft": True},
        source_module=__name__,
        actor_id=actor_id,
    )
    return draft


def _generate_with_openai(product: Product) -> StoryCardDraft | None:
    model = model_for("product_story")
    client = get_openai_compatible_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(product)},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    payload = json.loads(content)
    if not isinstance(payload, dict):
        return None
    return StoryCardDraft(
        what_it_is=_clean(payload.get("what_it_is")),
        who_it_is_for=_clean(payload.get("who_it_is_for")),
        materials=_clean(payload.get("materials")),
        customization_options=_clean(payload.get("customization_options")),
        internal_compliance_notes=_clean(payload.get("internal_compliance_notes")),
        model=model,
    )


def _build_prompt(product: Product) -> str:
    license_status = product.license_status.value if product.license_status else "unknown"
    compliance_context = {
        "license_status": license_status,
        "model_commercial_use_allowed": product.model_commercial_use_allowed,
        "model_license_type": product.model_license_type,
        "model_source_url": product.model_source_url,
        "model_designer_name": product.model_designer_name,
        "design_source": product.design_source,
        "commercial_license_notes": product.commercial_license_notes,
        "model_notes": product.model_notes,
        "model_proof_of_license_path": bool(product.model_proof_of_license_path),
        "needs_review": license_status in _AT_RISK_LICENSE_STATUSES,
    }
    product_context = {
        "name": product.name,
        "short_description": product.short_description,
        "description": product.description,
        "category": product.category.name if product.category else None,
        "care_instructions": product.care_instructions,
        "safety_notes": product.safety_notes,
        "tags": product.tags,
        "base_price": str(product.base_price) if product.base_price is not None else None,
        "estimated_print_minutes": product.estimated_print_minutes,
    }
    lines = [
        "Fill the Product Story Card for this product.",
        "Product data:",
        json.dumps(product_context, default=str),
        "Compliance / license data (use for the internal compliance note only):",
        json.dumps(compliance_context, default=str),
        (
            "Rule: if compliance_context.needs_review is true, the internal compliance note "
            "must clearly state the design license needs review before public sale and must "
            "not claim commercial rights."
        ),
    ]
    return "\n".join(lines)


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    return value or None
