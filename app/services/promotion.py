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


def generate_ai_assisted_draft(
    source_type: str,
    source_id: int,
    actor_id: int | None = None,
) -> ContentDraft | None:
    from flask import current_app

    ai_enabled = bool(current_app.config.get("AI_RECEIPT_PARSING_ENABLED", False) or
                      current_app.config.get("AI_ANALYTICS_INSIGHTS_ENABLED", False))
    openai_key = current_app.config.get("OPENAI_API_KEY", "")

    if ai_enabled and openai_key:
        try:
            return _generate_with_openai(source_type, source_id, actor_id)
        except Exception:
            current_app.logger.warning("AI draft generation failed, falling back to deterministic")
            return _generate_deterministic(source_type, source_id, actor_id)
    return _generate_deterministic(source_type, source_id, actor_id)


def _generate_with_openai(source_type: str, source_id: int, actor_id: int | None = None) -> ContentDraft | None:
    from flask import current_app
    import json

    context = _build_source_context(source_type, source_id)
    if context is None:
        return None

    prompt = (
        "You are a social media content assistant for Dude Fish Printing, a family-run 3D printing business. "
        "Generate a social media post draft based on the following context. "
        "Respond with JSON: {\"title\": \"...\", \"caption\": \"...\", \"channel\": \"facebook|instagram|tiktok\", \"content_type\": \"social_post\"}. "
        "Keep the caption under 300 characters. Do not invent fake reviews, fake testimonials, or unsupported claims. "
        f"Context: {json.dumps(context)}"
    )

    try:
        import httpx
        api_key = current_app.config["OPENAI_API_KEY"]
        model = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
    except Exception:
        raise

    channel_raw = result.get("channel", "facebook")
    try:
        channel = ContentChannel(channel_raw)
    except ValueError:
        channel = ContentChannel.FACEBOOK
    draft = ContentDraft(
        title=result.get("title", f"{source_type.title()} Spotlight"),
        content_type=result.get("content_type", "social_post"),
        channel=channel,
        caption=result.get("caption", ""),
        status=ContentStatus.DRAFT,
        created_by_user_id=actor_id,
    )
    _apply_source_field(draft, source_type, source_id)
    db.session.add(draft)
    db.session.commit()
    record_audit_event(
        action=f"content_draft.ai_generated_from_{source_type}",
        entity_type="content_draft",
        entity_id=draft.id,
        after_state={"title": draft.title, "source": source_type, "ai_assisted": True},
        source_module=__name__,
        actor_id=actor_id,
    )
    return draft


def _generate_deterministic(source_type: str, source_id: int, actor_id: int | None = None) -> ContentDraft | None:
    if source_type == "product":
        return generate_draft_from_product(source_id, actor_id)
    elif source_type == "market":
        return generate_draft_from_market(source_id, actor_id)
    elif source_type in ("custom_request", "custom-order"):
        return generate_draft_from_custom_request(source_id, actor_id)
    return None


def _build_source_context(source_type: str, source_id: int) -> dict | None:
    if source_type == "product":
        product = db.session.get(Product, source_id)
        if product is None:
            return None
        return {"type": "product", "name": product.name, "description": product.short_description or "", "price": float(product.base_price) if product.base_price else None}
    elif source_type == "market":
        market = db.session.get(Market, source_id)
        if market is None:
            return None
        return {"type": "market", "name": market.name, "city": market.city, "state": market.state, "date": str(market.event_date) if market.event_date else None}
    elif source_type in ("custom_request", "custom-order"):
        cr = db.session.get(CustomRequest, source_id)
        if cr is None:
            return None
        return {"type": "custom_order", "description": cr.description or ""}
    return None


def _apply_source_field(draft: ContentDraft, source_type: str, source_id: int) -> None:
    field_map = {"product": "product_id", "market": "market_id", "custom_request": "custom_request_id", "custom-order": "custom_request_id"}
    field = field_map.get(source_type)
    if field:
        setattr(draft, field, source_id)


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


def _generate_qr_svg(target_url: str | None) -> str:
    if not target_url:
        return ""
    import io
    import qrcode
    from qrcode.image.svg import SvgPathImage

    qr = qrcode.make(target_url, image_factory=SvgPathImage)
    buf = io.BytesIO()
    qr.save(buf)
    return buf.getvalue().decode("utf-8")


def generate_ai_sign_image(sign: SignAsset) -> SignAsset:
    from flask import current_app
    import io, uuid, httpx
    from PIL import Image

    ai_enabled = bool(current_app.config.get("AI_RECEIPT_PARSING_ENABLED", False) or
                      current_app.config.get("AI_ANALYTICS_INSIGHTS_ENABLED", False))
    api_key = current_app.config.get("OPENAI_API_KEY", "")
    if not ai_enabled or not api_key:
        return sign

    prompt_parts = [f"A professional market display sign for 3D printed products."]
    if sign.product:
        prompt_parts.append(f"Product: {sign.product.name}")
        if sign.product.short_description:
            prompt_parts.append(f"Description: {sign.product.short_description[:200]}")
    if sign.subtitle:
        prompt_parts.append(f"Subtitle: {sign.subtitle}")
    if sign.price_display:
        prompt_parts.append(f"Price: {sign.price_display}")
    prompt = ". ".join(prompt_parts) + ". Clean product photography style, warm inviting colors, solid background, no logos, no text rendering."

    image_url = None
    for model, size_val in [("dall-e-3", "1024x1024"), ("dall-e-2", "1024x1024")]:
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "prompt": prompt, "n": 1, "size": size_val},
                timeout=30,
            )
            if not resp.is_success:
                body = resp.text
                current_app.logger.warning("OpenAI %s error (status %s): %s", model, resp.status_code, body[:300])
                continue
            resp.raise_for_status()
            data = resp.json()
            image_url = data["data"][0]["url"]
            break
        except Exception as exc:
            current_app.logger.warning("AI sign image generation failed with %s: %s", model, exc)
            continue

    if image_url is None:
        return sign

    try:
        img_resp = httpx.get(image_url, timeout=30)
        img_resp.raise_for_status()
        img = Image.open(io.BytesIO(img_resp.content))

        if sign.qr_target_url:
            import qrcode as qrcode_lib
            qr_img = qrcode_lib.make(sign.qr_target_url, box_size=12, border=2).convert("RGB")
            qr_size = int(img.width * 0.2)
            qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
            margin = 20
            pos = (img.width - qr_size - margin, img.height - qr_size - margin)
            img.paste(qr_img, pos)

        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)
        png_bytes = buf.getvalue()

        from app.services.storage import upload_bytes_to_storage, image_storage_key
        bucket = current_app.config.get("SIGN_STORAGE_BUCKET", "signs")
        key = image_storage_key(sign.id, f"ai_sign_{uuid.uuid4().hex[:8]}.png")
        local_root = current_app.config.get("UPLOAD_FOLDER", "uploads")
        ref = upload_bytes_to_storage(png_bytes, bucket=bucket, key=key, local_root=local_root, content_type="image/png")

        sign.layout = "graphical"
        sign.ai_image_path = ref
        sign.generated_html = None
        sign.preview_html = None
        db.session.commit()
        record_audit_event(
            action="sign_asset.ai_image_generated",
            entity_type="sign_asset",
            entity_id=sign.id,
            after_state={"layout": "graphical", "ai_image_path": ref},
            source_module=__name__,
        )
    except Exception as exc:
        current_app.logger.warning("Failed to save AI sign image: %s", exc)
    return sign


def _product_image_html(sign: SignAsset) -> str:
    if not sign.product:
        return ""
    product = sign.product
    img_path = product.default_image_path
    if not img_path and product.images:
        img_path = product.images[0].file_path
    if not img_path:
        return ""
    from flask import url_for
    try:
        img_url = url_for("static", filename=img_path.lstrip("/"))
    except Exception:
        img_url = img_path
    return f'<img class="sign-product-image" src="{img_url}" alt="{product.name}" />'


def generate_sign_html(sign: SignAsset) -> str:
    price_html = f"<p class=\"sign-price\">{sign.price_display}</p>" if sign.price_display else ""
    subtitle_html = f"<p class=\"sign-subtitle\">{sign.subtitle}</p>" if sign.subtitle else ""
    desc_html = f"<p class=\"sign-description\">{sign.short_description}</p>" if sign.short_description else ""
    care_html = f"<p class=\"sign-care\">{sign.care_note}</p>" if sign.care_note else ""
    qr_html = _generate_qr_svg(sign.qr_target_url)
    img_html = _product_image_html(sign)
    qr_section = f'<div class="sign-qr">{qr_html}</div>' if qr_html else ""

    return f"""<div class="sign-container">
  <div class="sign-content">
    <h1 class="sign-title">{sign.title}</h1>
    {subtitle_html}
    {price_html}
    {desc_html}
    {care_html}
    {img_html}
    {qr_section}
  </div>
</div>"""


def save_sign_html(sign: SignAsset) -> SignAsset:
    sign.generated_html = generate_sign_html(sign)
    sign.preview_html = sign.generated_html
    db.session.commit()
    return sign


def generate_signs_for_market(market_id: int, actor_id: int | None = None) -> list[SignAsset]:
    market = db.session.get(Market, market_id)
    if market is None:
        return []
    from app.models.market import MarketPackingList

    packing_items = MarketPackingList.query.filter_by(market_id=market_id).all()
    product_ids = {item.product_id for item in packing_items}

    created: list[SignAsset] = []
    for pid in product_ids:
        product = db.session.get(Product, pid)
        if product is None:
            continue
        existing = SignAsset.query.filter_by(product_id=pid, market_id=market_id, status=SignStatus.DRAFT).first()
        if existing:
            continue
        sign = SignAsset(
            title=f"{product.name}",
            subtitle=f"At {market.name}",
            price_display=f"${float(product.base_price):.2f}" if product.base_price and product.base_price > 0 else None,
            short_description=product.short_description or "",
            status=SignStatus.DRAFT,
            product_id=product.id,
            market_id=market.id,
            is_active=True,
        )
        db.session.add(sign)
        save_sign_html(sign)
        created.append(sign)
        record_audit_event(
            action="sign_asset.generated_from_market",
            entity_type="sign_asset",
            entity_id=sign.id,
            after_state={"title": sign.title, "market_id": market.id, "product_id": product.id},
            source_module=__name__,
            actor_id=actor_id,
        )
    return created


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
