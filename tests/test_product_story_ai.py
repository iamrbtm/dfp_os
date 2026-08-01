from __future__ import annotations

import json

from app.extensions import db
from app.models import Category, LicenseStatus, Product, ProductStatus, ProductType
from app.services.product_story_ai import StoryCardDraft, generate_story_card_draft


def _product(**overrides) -> Product:
    category = Category(name="AI Dragons", slug="ai-dragons", is_public=True)
    data = {
        "name": "Story Dragon",
        "slug": "story-dragon",
        "sku_base": "AI-DRAGON",
        "short_description": "A shelf-ready articulated dragon.",
        "description": "A shelf-ready articulated dragon for market tables.",
        "category": category,
        "product_type": ProductType.FINISHED_GOOD,
        "status": ProductStatus.DRAFT,
        "is_public": False,
        "is_pos_visible": True,
        "base_price": 24,
        "license_status": LicenseStatus.COMMERCIAL_ALLOWED,
        "model_commercial_use_allowed": True,
        "model_license_type": "Commercial - Paid",
    }
    data.update(overrides)
    product = Product(**data)
    db.session.add(product)
    db.session.commit()
    return product


def _enable_ai(app) -> None:
    app.config["AI_PRODUCT_STORY_ENABLED"] = True
    app.config["OPENAI_API_KEY"] = "test-key"
    app.config["OPENAI_MODEL_PRODUCT_STORY"] = "gpt-test"


def test_generate_story_card_draft_disabled_returns_none(app):
    with app.app_context():
        app.config["AI_PRODUCT_STORY_ENABLED"] = False
        product = _product()
        assert generate_story_card_draft(product, actor_id=1) is None


def test_generate_story_card_draft_enabled_parses_openai_json(app, monkeypatch):
    class FakeMessage:
        content = json.dumps(
            {
                "what_it_is": "A flexible articulated dragon.",
                "who_it_is_for": "Gift buyers and market shoppers.",
                "materials": "PLA silk filament.",
                "customization_options": "Pick a color palette.",
                "internal_compliance_notes": "Commercial license on file; review before sale.",
            }
        )

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            pass

        chat = FakeChat()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    with app.app_context():
        _enable_ai(app)
        product = _product()
        draft = generate_story_card_draft(product, actor_id=42)

        assert draft is not None
        assert draft.what_it_is == "A flexible articulated dragon."
        assert draft.who_it_is_for == "Gift buyers and market shoppers."
        assert draft.materials == "PLA silk filament."
        assert draft.customization_options == "Pick a color palette."
        assert draft.internal_compliance_notes == "Commercial license on file; review before sale."


def test_generate_story_card_draft_audit_dispatched(app, monkeypatch):
    calls = []

    def fake_record(self, **payload):
        calls.append(payload)
        return {"id": "audit-story"}

    monkeypatch.setattr("app.services.audit_client.AuditClient.record", fake_record)

    class FakeMessage:
        content = json.dumps({"what_it_is": "A dragon."})

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            pass

        chat = FakeChat()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    with app.app_context():
        _enable_ai(app)
        product = _product()
        generate_story_card_draft(product, actor_id=7)

    assert any(call["action"] == "product_story_card.ai_generated" for call in calls)


def test_generate_story_card_falls_back_cleanly_on_openai_error(app, monkeypatch):
    def boom(self, **kwargs):
        raise RuntimeError("network down")

    class FakeCompletions:
        create = boom

    class FakeChat:
        completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            pass

        chat = FakeChat()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    with app.app_context():
        _enable_ai(app)
        product = _product()
        draft = generate_story_card_draft(product, actor_id=1)
        assert draft is None


def test_story_card_generate_route_returns_400_when_disabled(client, app, login_admin):
    app.config["AI_PRODUCT_STORY_ENABLED"] = False
    with app.app_context():
        product = _product()
        product_id = product.id
    resp = client.post(f"/products/studio/{product_id}/story-card/generate")
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_story_card_generate_route_returns_draft_and_does_not_persist(
    client, app, login_admin, monkeypatch
):
    _enable_ai(app)

    def fake_generate(product, *, actor_id=None):
        return StoryCardDraft(
            what_it_is="A dragon.",
            who_it_is_for="Shoppers.",
            materials="PLA.",
            customization_options="Colors.",
            internal_compliance_notes="License on file.",
            model="gpt-test",
        )

    monkeypatch.setattr(
        "app.services.product_story_ai._generate_with_openai",
        lambda product: fake_generate(product),
    )

    with app.app_context():
        product = _product()
        product_id = product.id

    resp = client.post(f"/products/studio/{product_id}/story-card/generate")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["data"]["story_what_it_is"] == "A dragon."
    assert payload["data"]["story_internal_compliance_notes"] == "License on file."

    with app.app_context():
        persisted = db.session.get(Product, product_id)
        assert persisted.story_what_it_is is None
