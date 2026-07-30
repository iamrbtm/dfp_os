"""Phase 1 — Launch Gate & Create Flow Integrity (Issues 1, 2, 42, 48, 55)."""

from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import Category, Product, ProductStatus, ProductType
from app.models.catalog import LicenseStatus
from app.services.product_ops import launch_gate


def _studio_data(category_id: int, **overrides) -> dict[str, str]:
    """Minimal form payload; defaults to an unready product (no price/license/model)."""
    data = {
        "name": "Phase1 Widget",
        "slug": "phase1-widget",
        "sku_base": "P1-WIDGET",
        "short_description": "A widget.",
        "description": "A widget.",
        "category_id": str(category_id),
        "product_type": "finished_good",
        "status": "draft",
        "license_status": "unknown",
        "model_source_type": "unknown",
        "base_price": "0",
        "submit": "Save Product",
    }
    data.update(overrides)
    return data


def _make_draft_product(app, *, name: str = "Phase1 Draft", slug: str = "phase1-draft") -> int:
    with app.app_context():
        category = Category(
            name="Phase1 Cats", slug="phase1-cats", is_public=True, is_pos_visible=True
        )
        product = Product(
            name=name,
            slug=slug,
            sku_base="P1-DRAFT",
            short_description="Draft.",
            description="Draft.",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.DRAFT,
            is_public=False,
            base_price=Decimal("0"),
            license_status=LicenseStatus.UNKNOWN,
            model_commercial_use_allowed=False,
        )
        db.session.add_all([category, product])
        db.session.commit()
        return product.id


# ---------------------------------------------------------------------------
# Issue 42 — server-side override validation (cannot be bypassed by raw data)
# ---------------------------------------------------------------------------


def _ready_product(app) -> Product:
    with app.app_context():
        category = Category(
            name="Ready Cats", slug="ready-cats", is_public=True, is_pos_visible=True
        )
        product = Product(
            name="Ready",
            slug="ready",
            sku_base="READY",
            description="x",
            short_description="x",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            is_public=True,
            base_price=Decimal("25"),
            license_status=LicenseStatus.COMMERCIAL_ALLOWED,
            model_commercial_use_allowed=True,
            safety_notes="none",
            care_instructions="none",
        )
        db.session.add_all([category, product])
        db.session.commit()
        return product


def test_launch_gate_rejects_empty_and_short_override(app):
    with app.app_context():
        category = Category(name="C2", slug="c2", is_public=True, is_pos_visible=True)
        product = Product(
            name="P",
            slug="p",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.DRAFT,
            base_price=Decimal("0"),
            license_status=LicenseStatus.UNKNOWN,
            model_commercial_use_allowed=False,
        )
        db.session.add_all([category, product])
        db.session.commit()

        product.launch_override_reason = "   "
        assert launch_gate(product)[0] is False  # whitespace does not bypass

        product.launch_override_reason = "lol"
        assert launch_gate(product)[0] is False  # too short

        product.launch_override_reason = "123456789"  # 9 chars
        assert launch_gate(product)[0] is False

        product.launch_override_reason = "Override reason here"  # 10+ chars
        assert launch_gate(product)[0] is True


# ---------------------------------------------------------------------------
# Issue 55 — override reason max length
# ---------------------------------------------------------------------------


def test_launch_gate_rejects_overlong_override(app):
    pid = _ready_product(app).id  # ensure app context seeds a category/slug set
    with app.app_context():
        product = db.session.get(Product, pid)
        product.launch_override_reason = "x" * 2001
        assert launch_gate(product)[0] is False
        product.launch_override_reason = "x" * 2000
        assert launch_gate(product)[0] is True


def test_form_rejects_overlong_override_and_accepts_boundary(app, client, login_admin):
    with app.app_context():
        category = Category(name="C3", slug="c3", is_public=True, is_pos_visible=True)
        db.session.add(category)
        db.session.commit()
        cid = category.id
    base = _studio_data(cid, status="draft")

    too_long = dict(base, launch_override_reason="x" * 3000)
    r = client.post("/products/studio", data=too_long, follow_redirects=False)
    assert r.status_code == 200  # form re-renders with a validation error

    boundary = dict(base, launch_override_reason="x" * 2000, slug="phase1-boundary")
    r = client.post("/products/studio", data=boundary, follow_redirects=False)
    assert r.status_code == 302


# ---------------------------------------------------------------------------
# Issue 2 — create flow is gated; unready products cannot go live
# ---------------------------------------------------------------------------


def test_create_active_unready_forced_to_draft(app, client, login_admin):
    with app.app_context():
        category = Category(
            name="CreateCats", slug="create-cats", is_public=True, is_pos_visible=True
        )
        db.session.add(category)
        db.session.commit()
        cid = category.id

    data = _studio_data(cid, status="active", is_public="y")
    r = client.post("/products/studio", data=data, follow_redirects=False)
    assert r.status_code == 302  # created (as draft), redirected to studio

    with app.app_context():
        product = Product.query.filter_by(slug="phase1-widget").one()
        assert product.status == ProductStatus.DRAFT
        assert product.is_public is False


def test_create_active_with_valid_override_goes_live(app, client, login_admin):
    with app.app_context():
        category = Category(
            name="CreateCats2", slug="create-cats2", is_public=True, is_pos_visible=True
        )
        db.session.add(category)
        db.session.commit()
        cid = category.id

    data = _studio_data(
        cid,
        status="active",
        is_public="y",
        slug="phase1-override",
        launch_override_reason="Manager approved this launch override.",
    )
    r = client.post("/products/studio", data=data, follow_redirects=False)
    assert r.status_code == 302

    with app.app_context():
        product = Product.query.filter_by(slug="phase1-override").one()
        assert product.status == ProductStatus.ACTIVE
        assert product.is_public is True


# ---------------------------------------------------------------------------
# Issue 1 / 48 — blocked edit must not persist
# ---------------------------------------------------------------------------


def test_blocked_edit_returns_400_and_does_not_persist(app, client, login_admin, monkeypatch):
    pid = _make_draft_product(app, slug="phase1-draft")

    # Spy on the persistence path; a blocked edit must never call it.
    calls: list[int] = []
    from app.blueprints.products import studio_routes

    real_update = studio_routes.update_admin_resource

    def spy(product, *, before_state=None, actor_id=None):
        calls.append(product.id)
        return real_update(product, before_state=before_state, actor_id=actor_id)

    monkeypatch.setattr(studio_routes, "update_admin_resource", spy)

    with app.app_context():
        category_id = db.session.get(Product, pid).category_id
    data = _studio_data(category_id, status="active", is_public="y", slug="phase1-draft")
    r = client.post(f"/products/studio/{pid}", data=data, follow_redirects=False)

    assert r.status_code == 400, "blocked launch edit must return 400"
    assert calls == [], "blocked edit must not persist (update_admin_resource not called)"

    with app.app_context():
        product = db.session.get(Product, pid)
        assert product.status == ProductStatus.DRAFT, "product must remain draft"
        assert product.is_public is False, "product must remain private"
        assert product.name == "Phase1 Draft", "blocked edits must not change fields"


def test_successful_edit_with_override_persists(app, client, login_admin, monkeypatch):
    pid = _make_draft_product(app, slug="phase1-draft-ok")

    calls: list[int] = []
    from app.blueprints.products import studio_routes

    real_update = studio_routes.update_admin_resource

    def spy(product, *, before_state=None, actor_id=None):
        calls.append(product.id)
        return real_update(product, before_state=before_state, actor_id=actor_id)

    monkeypatch.setattr(studio_routes, "update_admin_resource", spy)

    with app.app_context():
        category_id = db.session.get(Product, pid).category_id
    data = _studio_data(
        category_id,
        status="active",
        is_public="y",
        slug="phase1-draft-ok",
        launch_override_reason="Manager approved this override launch.",
    )
    r = client.post(f"/products/studio/{pid}", data=data, follow_redirects=False)
    assert r.status_code == 302
    assert calls == [pid], "successful edit must persist exactly once"

    with app.app_context():
        product = db.session.get(Product, pid)
        assert product.status == ProductStatus.ACTIVE
        assert product.is_public is True
