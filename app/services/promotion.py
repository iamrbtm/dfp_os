from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flask import url_for
from flask_login import current_user

from app.extensions import db
from app.models import CustomRequest, Market, Product
from app.models.promotion import (
    ContentChannel,
    ContentDraft,
    ContentStatus,
    SignAsset,
    SignStatus,
)
from app.services.audit import record_audit_event


def generate_draft_from_product(product_id: int, actor_id: int | None = None) -> ContentDraft | None:
    product = db.session.get(Product, product_id)
    if product is None:
        return None
    title = f"Product Spotlight: {product.name}"
    draft = ContentDraft(
        title=title,
        content_type="social_post",
        channel=ContentChannel.FACEBOOK,
        caption=_build_product_caption(product),
        product_id=product.id,
        status=ContentStatus.DRAFT,
        created_by_user_id=actor_id,
    )
    db.session.add(draft)
    db.session.commit()
    record_audit_event(
        action="content_draft.generated_from_product",
        entity_type="content_draft",
        entity_id=draft.id,
        after_state={"title": draft.title, "product_id": product.id, "source": "product"},
        source_module=__name__,
        actor_id=actor_id,
    )
    return draft


def generate_draft_from_market(market_id: int, actor_id: int | None = None) -> ContentDraft | None:
    market = db.session.get(Market, market_id)
    if market is None:
        return None
    title = f"We\u2019ll be at {market.name}!"
    draft = ContentDraft(
        title=title,
        content_type="social_post",
        channel=ContentChannel.FACEBOOK,
        caption=_build_market_caption(market),
        market_id=market.id,
        status=ContentStatus.DRAFT,
        created_by_user_id=actor_id,
    )
    db.session.add(draft)
    db.session.commit()
    record_audit_event(
        action="content_draft.generated_from_market",
        entity_type="content_draft",
        entity_id=draft.id,
        after_state={"title": draft.title, "market_id": market.id, "source": "market"},
        source_module=__name__,
        actor_id=actor_id,
    )
    return draft


def generate_draft_from_custom_request(cr_id: int, actor_id: int | None = None) -> ContentDraft | None:
    cr = db.session.get(CustomRequest, cr_id)
    if cr is None:
        return None
    title = "Custom Order Completed!"
    draft = ContentDraft(
        title=title,
        content_type="social_post",
        channel=ContentChannel.FACEBOOK,
        caption=_build_custom_request_caption(cr),
        custom_request_id=cr.id,
        status=ContentStatus.DRAFT,
        created_by_user_id=actor_id,
    )
    db.session.add(draft)
    db.session.commit()
    record_audit_event(
        action="content_draft.generated_from_custom_request",
        entity_type="content_draft",
        entity_id=draft.id,
        after_state={"title": draft.title, "custom_request_id": cr.id, "source": "custom_request"},
        source_module=__name__,
        actor_id=actor_id,
    )
    return draft


def _build_product_caption(product: Product) -> str:
    parts = [f"Check out the {product.name}!"]
    if product.short_description:
        parts.append(product.short_description)
    if product.base_price and product.base_price > 0:
        parts.append(f"Only ${float(product.base_price):.2f}!")
    return " ".join(parts)


def _build_market_caption(market: Market) -> str:
    parts = [f"Come see us at {market.name}!"]
    if market.city and market.state:
        parts.append(f"📍 {market.city}, {market.state}")
    if market.event_date:
        parts.append(f"📅 {market.event_date.strftime('%B %d, %Y')}")
    return " ".join(parts)


def _build_custom_request_caption(cr: CustomRequest) -> str:
    parts = ["A custom order we just finished!"]
    if cr.description:
        parts.append(f"Customer wanted: {cr.description[:200]}")
    return " ".join(parts)


def approve_draft(draft: ContentDraft, actor: Any | None = None) -> ContentDraft:
    draft.status = ContentStatus.APPROVED
    db.session.commit()
    record_audit_event(
        action="content_draft.approved",
        entity_type="content_draft",
        entity_id=draft.id,
        before_state={"status": ContentStatus.NEEDS_REVIEW.value},
        after_state={"status": ContentStatus.APPROVED.value, "title": draft.title},
        source_module=__name__,
        actor_id=getattr(actor, "id", None),
    )
    return draft


def publish_draft(draft: ContentDraft, actor: Any | None = None) -> ContentDraft:
    draft.status = ContentStatus.PUBLISHED
    draft.published_at = datetime.now(timezone.utc)
    db.session.commit()
    record_audit_event(
        action="content_draft.published",
        entity_type="content_draft",
        entity_id=draft.id,
        before_state={"status": ContentStatus.APPROVED.value},
        after_state={"status": ContentStatus.PUBLISHED.value, "title": draft.title},
        source_module=__name__,
        actor_id=getattr(actor, "id", None),
    )
    return draft


def archive_draft(draft: ContentDraft, actor: Any | None = None) -> ContentDraft:
    draft.status = ContentStatus.ARCHIVED
    db.session.commit()
    record_audit_event(
        action="content_draft.archived",
        entity_type="content_draft",
        entity_id=draft.id,
        before_state={"status": draft.status.value if hasattr(draft.status, "value") else str(draft.status)},
        after_state={"status": ContentStatus.ARCHIVED.value},
        source_module=__name__,
        actor_id=getattr(actor, "id", None),
    )
    return draft


def generate_sign_html(sign: SignAsset) -> str:
    price_html = f"<p class=\"sign-price\">{sign.price_display}</p>" if sign.price_display else ""
    subtitle_html = f"<p class=\"sign-subtitle\">{sign.subtitle}</p>" if sign.subtitle else ""
    desc_html = f"<p class=\"sign-description\">{sign.short_description}</p>" if sign.short_description else ""
    care_html = f"<p class=\"sign-care\">{sign.care_note}</p>" if sign.care_note else ""

    return f"""<div class="sign-container">
  <div class="sign-content">
    <h1 class="sign-title">{sign.title}</h1>
    {subtitle_html}
    {price_html}
    {desc_html}
    {care_html}
  </div>
</div>"""


def save_sign_html(sign: SignAsset) -> SignAsset:
    sign.generated_html = generate_sign_html(sign)
    sign.preview_html = sign.generated_html
    db.session.commit()
    return sign


def approve_sign(sign: SignAsset, actor: Any | None = None) -> SignAsset:
    sign.status = SignStatus.APPROVED
    db.session.commit()
    record_audit_event(
        action="sign_asset.approved",
        entity_type="sign_asset",
        entity_id=sign.id,
        source_module=__name__,
        actor_id=getattr(actor, "id", None),
    )
    return sign


def archive_sign(sign: SignAsset, actor: Any | None = None) -> SignAsset:
    sign.status = SignStatus.ARCHIVED
    db.session.commit()
    record_audit_event(
        action="sign_asset.archived",
        entity_type="sign_asset",
        entity_id=sign.id,
        source_module=__name__,
        actor_id=getattr(actor, "id", None),
    )
    return sign
