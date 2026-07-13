from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.extensions import db
from app.models import Category, CustomRequest, CustomRequestStatus, Market, MarketStatus, Product, ProductStatus, ProductType, UserRole
from app.models.promotion import ContentChannel, ContentDraft, ContentStatus, SignAsset, SignStatus
from app.services.admin_mutations import create_resource, snapshot_instance, update_resource
from app.services.api_tokens import create_api_token
from app.services.promotion import (
    approve_draft,
    approve_sign,
    archive_draft,
    archive_sign,
    generate_ai_assisted_draft,
    generate_draft_from_custom_request,
    generate_draft_from_market,
    generate_draft_from_product,
    generate_sign_html,
    generate_signs_for_market,
    publish_draft,
    save_sign_html,
)


def _scoped_token(client, *scopes: str) -> str:
    from app.models import User

    with client.application.app_context():
        user = User(
            email=f"{'-'.join(scopes)}-promo@example.com",
            first_name="Promo",
            last_name="Test",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        _token, raw = create_api_token(user, "Promo API Token", scopes=list(scopes))
        return raw


def _ensure_category():
    cat = Category.query.filter_by(slug="promo-test-cat").first()
    if not cat:
        cat = Category(name="Promo Test", slug="promo-test-cat", is_public=True, is_pos_visible=True)
        db.session.add(cat)
        db.session.flush()
    return cat


def _ensure_product():
    cat = _ensure_category()
    product = Product.query.filter_by(slug="promo-test-prod").first()
    if not product:
        product = Product(
            name="Promo Test Product",
            slug="promo-test-prod",
            category_id=cat.id,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            base_price=12.99,
            is_public=True,
            is_pos_visible=True,
        )
        db.session.add(product)
        db.session.flush()
    return product


# --- Model Tests ---

def test_content_draft_model_can_be_created(app):
    with app.app_context():
        draft = ContentDraft(
            title="Test Draft",
            content_type="social_post",
            channel=ContentChannel.FACEBOOK,
            caption="Check out our new products!",
            status=ContentStatus.DRAFT,
        )
        db.session.add(draft)
        db.session.commit()

        assert draft.id is not None
        assert draft.title == "Test Draft"
        assert draft.channel == ContentChannel.FACEBOOK
        assert draft.status == ContentStatus.DRAFT


def test_content_draft_status_choices(app):
    with app.app_context():
        for status in ContentStatus:
            draft = ContentDraft(
                title=f"Status {status.value}",
                content_type="social_post",
                channel=ContentChannel.INSTAGRAM,
                status=status,
            )
            db.session.add(draft)
        db.session.commit()
        assert ContentDraft.query.count() == len(list(ContentStatus))


def test_sign_asset_model_can_be_created(app):
    with app.app_context():
        sign = SignAsset(
            title="Rainbow Dragon Sign",
            subtitle="Our best seller!",
            price_display="$12",
            short_description="A beautiful articulated dragon.",
            status=SignStatus.DRAFT,
        )
        db.session.add(sign)
        db.session.commit()

        assert sign.id is not None
        assert sign.title == "Rainbow Dragon Sign"
        assert sign.status == SignStatus.DRAFT


def test_sign_asset_linked_to_product(app):
    with app.app_context():
        product = _ensure_product()
        sign = SignAsset(
            title="Product Sign",
            product_id=product.id,
            status=SignStatus.DRAFT,
        )
        db.session.add(sign)
        db.session.commit()

        assert sign.product is not None
        assert sign.product.name == "Promo Test Product"


# --- Service Tests ---

def test_generate_draft_from_product(app):
    with app.app_context():
        product = _ensure_product()
        draft = generate_draft_from_product(product.id, actor_id=1)

        assert draft is not None
        assert draft.product_id == product.id
        assert draft.status == ContentStatus.DRAFT
        assert "Promo Test Product" in draft.title
        assert draft.caption is not None


def test_generate_draft_from_market(app):
    with app.app_context():
        market = Market(
            name="Test Market Promo",
            city="Clarksville",
            state="TN",
            status=MarketStatus.SCHEDULED,
        )
        db.session.add(market)
        db.session.commit()

        draft = generate_draft_from_market(market.id, actor_id=1)

        assert draft is not None
        assert draft.market_id == market.id
        assert "Test Market Promo" in draft.title
        assert "Clarksville" in draft.caption


def test_generate_draft_from_custom_request(app):
    with app.app_context():
        cr = CustomRequest(
            name="Test Customer",
            email="customer@example.com",
            description="I want a custom dragon in purple.",
            status=CustomRequestStatus.NEW,
        )
        db.session.add(cr)
        db.session.commit()

        draft = generate_draft_from_custom_request(cr.id, actor_id=1)

        assert draft is not None
        assert draft.custom_request_id == cr.id
        assert "Custom Order Completed" in draft.title


def test_draft_approve_and_publish_workflow(app):
    with app.app_context():
        draft = ContentDraft(
            title="Approve Test",
            content_type="social_post",
            channel=ContentChannel.FACEBOOK,
            status=ContentStatus.DRAFT,
        )
        db.session.add(draft)
        db.session.commit()

        draft.status = ContentStatus.NEEDS_REVIEW
        db.session.commit()
        approve_draft(draft)
        assert draft.status == ContentStatus.APPROVED

        publish_draft(draft)
        assert draft.status == ContentStatus.PUBLISHED
        assert draft.published_at is not None


def test_draft_archive(app):
    with app.app_context():
        draft = ContentDraft(
            title="Archive Test",
            content_type="social_post",
            channel=ContentChannel.INSTAGRAM,
            status=ContentStatus.DRAFT,
        )
        db.session.add(draft)
        db.session.commit()

        archive_draft(draft)
        assert draft.status == ContentStatus.ARCHIVED


def test_generate_sign_html(app):
    with app.app_context():
        sign = SignAsset(
            title="Test Sign",
            price_display="$10",
            short_description="A test product.",
            care_note="Hand wash only.",
            status=SignStatus.DRAFT,
        )
        html = generate_sign_html(sign)
        assert "Test Sign" in html
        assert "$10" in html
        assert "Hand wash only" in html


def test_save_sign_html(app):
    with app.app_context():
        sign = SignAsset(
            title="Save Test",
            price_display="$5",
            status=SignStatus.DRAFT,
        )
        db.session.add(sign)
        db.session.commit()

        save_sign_html(sign)
        assert sign.generated_html is not None
        assert sign.preview_html is not None
        assert "Save Test" in sign.generated_html


def test_sign_approve(app):
    with app.app_context():
        sign = SignAsset(
            title="Approve Sign",
            status=SignStatus.DRAFT,
        )
        db.session.add(sign)
        db.session.commit()

        approve_sign(sign)
        assert sign.status == SignStatus.APPROVED


def test_sign_archive(app):
    with app.app_context():
        sign = SignAsset(
            title="Archive Sign",
            status=SignStatus.DRAFT,
        )
        db.session.add(sign)
        db.session.commit()

        archive_sign(sign)
        assert sign.status == SignStatus.ARCHIVED


def test_draft_generation_handles_missing_product(app):
    with app.app_context():
        draft = generate_draft_from_product(99999)
        assert draft is None


def test_draft_admin_routes_require_auth(client):
    resp = client.get("/promotion/")
    assert resp.status_code == 302


def test_sign_admin_routes_require_auth(client):
    resp = client.get("/promotion/signs/")
    assert resp.status_code == 302


def test_draft_admin_create_flow(app, client):
    with app.app_context():
        from app.models import User
        user = User.query.filter_by(role=UserRole.ADMIN).first()
        if user is None:
            user = User(
                email="promo-admin@example.com",
                first_name="Promo",
                last_name="Admin",
                role=UserRole.ADMIN,
                is_active=True,
            )
            user.set_password("secret")
            db.session.add(user)
            db.session.commit()

    client.post("/auth/login", data={
        "email": "promo-admin@example.com",
        "password": "secret",
    }, follow_redirects=True)

    resp = client.post("/promotion/drafts/new", data={
        "title": "Test Draft from UI",
        "channel": "facebook",
        "content_type": "social_post",
        "caption": "This is a test draft.",
        "status": "draft",
    }, follow_redirects=True)

    assert resp.status_code in (200, 302)


def test_sign_asset_admin_api_token_enforcement(client):
    resp = client.post(
        "/api/v1/promotion/signs",
        json={"title": "Should fail", "status": "draft"},
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code in (401, 403)


def test_prep_task_model_create_audit_dispatched(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-test"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        draft = ContentDraft(
            title="Audit Draft",
            content_type="social_post",
            channel=ContentChannel.FACEBOOK,
            status=ContentStatus.DRAFT,
        )
        create_resource(draft, actor_id=123)

    assert any(call["action"] == "content_draft.created" for call in calls)


def test_ai_assisted_draft_falls_back_to_deterministic_when_ai_disabled(app):
    with app.app_context():
        from flask import current_app
        current_app.config["AI_RECEIPT_PARSING_ENABLED"] = False
        current_app.config["AI_ANALYTICS_INSIGHTS_ENABLED"] = False
        current_app.config["OPENAI_API_KEY"] = ""

        product = _ensure_product()
        draft = generate_ai_assisted_draft("product", product.id, actor_id=1)

        assert draft is not None
        assert draft.product_id == product.id
        assert draft.status == ContentStatus.DRAFT
        assert "Promo Test Product" in draft.title


def test_ai_assisted_draft_from_market_falls_back_when_disabled(app):
    with app.app_context():
        from flask import current_app
        current_app.config["AI_RECEIPT_PARSING_ENABLED"] = False
        current_app.config["OPENAI_API_KEY"] = ""

        market = Market(
            name="AI Fallback Market",
            city="Clarksville",
            state="TN",
            status=MarketStatus.SCHEDULED,
        )
        db.session.add(market)
        db.session.commit()

        draft = generate_ai_assisted_draft("market", market.id, actor_id=1)

        assert draft is not None
        assert draft.market_id == market.id
        assert "AI Fallback Market" in draft.title


def test_ai_assisted_draft_handles_unknown_source(app):
    with app.app_context():
        draft = generate_ai_assisted_draft("unknown_source", 1, actor_id=1)
        assert draft is None


def test_ai_assisted_draft_dispatches_audit_event(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-ai-fallback"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        from flask import current_app
        current_app.config["AI_RECEIPT_PARSING_ENABLED"] = False
        current_app.config["OPENAI_API_KEY"] = ""

        product = _ensure_product()
        generate_ai_assisted_draft("product", product.id, actor_id=42)

    assert any(call["action"] == "content_draft.generated_from_product" for call in calls)


def test_generate_signs_for_market_creates_signs(app):
    with app.app_context():
        product = _ensure_product()
        from app.models.market import MarketPackingList
        market = Market(
            name="Sign Test Market",
            city="Clarksville",
            state="TN",
            status=MarketStatus.SCHEDULED,
        )
        db.session.add(market)
        db.session.flush()
        packing = MarketPackingList(market_id=market.id, product_id=product.id)
        db.session.add(packing)
        db.session.commit()

        signs = generate_signs_for_market(market.id)
        assert len(signs) >= 1
        assert any(s.product_id == product.id for s in signs)


def test_generate_signs_for_market_skips_existing(app):
    with app.app_context():
        product = _ensure_product()
        from app.models.market import MarketPackingList
        market = Market(
            name="Skip Test Market",
            city="Clarksville",
            state="TN",
            status=MarketStatus.SCHEDULED,
        )
        db.session.add(market)
        db.session.flush()
        packing = MarketPackingList(market_id=market.id, product_id=product.id)
        db.session.add(packing)
        db.session.commit()

        generate_signs_for_market(market.id)
        second_batch = generate_signs_for_market(market.id)
        assert len(second_batch) == 0


def test_generate_sign_html_includes_qr_when_url_set(app):
    with app.app_context():
        sign = SignAsset(
            title="QR Sign",
            qr_target_url="https://dudefishprinting.com/shop/rainbow-dragon",
            status=SignStatus.DRAFT,
        )
        db.session.add(sign)
        db.session.commit()

        html = generate_sign_html(sign)
        assert "sign-qr" in html
        assert "svg" in html


def test_generate_sign_html_omits_qr_when_url_empty(app):
    with app.app_context():
        sign = SignAsset(
            title="No QR Sign",
            status=SignStatus.DRAFT,
        )
        html = generate_sign_html(sign)
        assert "sign-qr" not in html


def test_generate_signs_for_market_returns_empty_for_missing(app):
    with app.app_context():
        signs = generate_signs_for_market(99999)
        assert signs == []


def test_generate_sign_html_includes_product_image_when_available(app):
    with app.app_context():
        product = _ensure_product()
        from app.models.catalog import ProductImage
        img = ProductImage(product_id=product.id, file_path="uploads/test.jpg", is_default=True)
        db.session.add(img)
        db.session.flush()
        sign = SignAsset(title="Image Sign", product_id=product.id, status=SignStatus.DRAFT)
        db.session.add(sign)
        db.session.commit()

        html = generate_sign_html(sign)
        assert "sign-product-image" in html


def test_sign_print_route_loads(client, app):
    with app.app_context():
        sign = SignAsset(title="Print Test Sign", status=SignStatus.DRAFT)
        db.session.add(sign)
        db.session.commit()
        sid = sign.id

    from app.models import User
    with app.app_context():
        user = User.query.filter_by(role=UserRole.ADMIN).first()
        if user is None:
            user = User(email="print-test@example.com", first_name="Print", last_name="Test", role=UserRole.ADMIN, is_active=True)
            user.set_password("secret")
            db.session.add(user)
            db.session.commit()

    client.post("/auth/login", data={"email": "print-test@example.com", "password": "secret"}, follow_redirects=True)
    resp = client.get(f"/promotion/signs/{sid}/print")
    assert resp.status_code in (200, 302)


def test_generate_signs_for_market_dispatches_audit(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-sign-market"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    with app.app_context():
        product = _ensure_product()
        from app.models.market import MarketPackingList
        market = Market(name="Audit Market Sign", city="Clarksville", state="TN", status=MarketStatus.SCHEDULED)
        db.session.add(market)
        db.session.flush()
        packing = MarketPackingList(market_id=market.id, product_id=product.id)
        db.session.add(packing)
        db.session.commit()

        generate_signs_for_market(market.id, actor_id=42)

    assert any(call["action"] == "sign_asset.generated_from_market" for call in calls)
