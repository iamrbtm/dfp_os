from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    Business,
    Category,
    Collection,
    FilamentSpool,
    Product,
    ProductStatus,
    ProductType,
)
from app.services.cost_engine import (
    CostResolverResult,
    calculate_product_cost,
    persist_cost_snapshot,
    resolve_material_cost,
)


def _make_spool(*, business_id, material_type, color, grams, cost_per_gram):
    return FilamentSpool(
        brand="brand",
        business_id=business_id,
        material_type=material_type,
        color_name=color,
        remaining_weight_grams=grams,
        cost_per_spool=Decimal("20.00"),
        cost_per_gram=cost_per_gram,
        status="active",
    )


def _make_product(*, business_id, slug, material=None, category_id=None, collection_id=None):
    return Product(
        name=slug,
        slug=slug,
        business_id=business_id,
        category_id=category_id,
        collection_id=collection_id,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
        is_public=True,
        is_pos_visible=True,
        base_price=Decimal("30.00"),
        estimated_labor_minutes=10,
        estimated_print_minutes=100,
        analysis_status="complete",
        parsed_filament_grams=Decimal("100"),
        parsed_print_minutes=Decimal("60"),
        model_analysis_config={"material": material} if material else None,
    )


def _catalog(app):
    with app.app_context():
        category = Category(
            name="C",
            slug="c",
            sort_order=1,
            is_public=True,
            is_pos_visible=True,
        )
        collection = Collection(name="Col", slug="col", is_public=True, sort_order=1)
        db.session.add_all([category, collection])
        db.session.flush()
        return category.id, collection.id


# ---------------------------------------------------------------------------
# Issue 13 / 47 — cross-business isolation + material matching
# ---------------------------------------------------------------------------


def test_resolve_material_cost_isolates_by_business(app):
    with app.app_context():
        biz_a = Business(name="A", slug="biz-a")
        biz_b = Business(name="B", slug="biz-b")
        db.session.add_all([biz_a, biz_b])
        db.session.flush()

        # Business A: two PLA spools -> weighted avg (1000*.02 + 500*.03)/1500
        db.session.add(
            _make_spool(
                business_id=biz_a.id,
                material_type="PLA",
                color="Red",
                grams=1000,
                cost_per_gram=Decimal("0.0200"),
            )
        )
        db.session.add(
            _make_spool(
                business_id=biz_a.id,
                material_type="PLA",
                color="Blue",
                grams=500,
                cost_per_gram=Decimal("0.0300"),
            )
        )
        # Business B: one PETG spool at a very different price
        db.session.add(
            _make_spool(
                business_id=biz_b.id,
                material_type="PETG",
                color="Black",
                grams=800,
                cost_per_gram=Decimal("0.0500"),
            )
        )
        db.session.commit()

        result_a = resolve_material_cost(biz_a.id, "PLA")
        assert result_a.cost_per_gram == Decimal("0.0233")
        assert result_a.confidence == "high"
        assert result_a.spool_id is not None

        result_b = resolve_material_cost(biz_b.id, "PETG")
        assert result_b.cost_per_gram == Decimal("0.0500")
        assert result_b.confidence == "high"

        # A PLA product must never pick up business B's PETG cost.
        assert result_a.cost_per_gram != result_b.cost_per_gram


def test_pla_product_does_not_use_petg_spool_costs(app):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.flush()
        db.session.add(
            _make_spool(
                business_id=biz.id,
                material_type="PETG",
                color="Black",
                grams=1000,
                cost_per_gram=Decimal("0.0800"),
            )
        )
        db.session.commit()

        # Product asks for PLA but business only has PETG -> fallback medium.
        resolver = resolve_material_cost(biz.id, "PLA")
        assert resolver.confidence == "medium"
        assert resolver.evidence["fallback_reason"] == "no_material_match"
        # Fallback averages the business's PETG spools, NOT a PLA price.
        assert resolver.cost_per_gram == Decimal("0.0800")

        product = _make_product(
            business_id=biz.id,
            slug="pla-product",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        db.session.add(product)
        db.session.commit()
        breakdown = calculate_product_cost(product=product)
        # Fallback confidence is medium; cost comes from the PETG-weighted avg.
        assert breakdown.confidence == "medium"
        assert breakdown.cost_per_gram == Decimal("0.0800")


def test_no_spools_fallback_is_explicit_none_confidence(app):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.commit()

        resolver = resolve_material_cost(biz.id, "PLA")
        assert resolver.cost_per_gram == Decimal("0.0000")
        assert resolver.confidence == "none"
        assert resolver.evidence["fallback_reason"] == "no_spools"
        assert resolver.spool_id is None

        product = _make_product(
            business_id=biz.id,
            slug="no-spool-product",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        db.session.add(product)
        db.session.commit()
        breakdown = calculate_product_cost(product=product)
        assert breakdown.cost_per_gram == Decimal("0.0000")
        assert breakdown.confidence == "none"
        assert breakdown.evidence_source == "no_spool_cost"


def test_spool_id_exact_match_is_high_confidence_and_business_scoped(app):
    with app.app_context():
        biz_a = Business(name="A", slug="biz-a")
        biz_b = Business(name="B", slug="biz-b")
        db.session.add_all([biz_a, biz_b])
        db.session.flush()
        spool_a = _make_spool(
            business_id=biz_a.id,
            material_type="PLA",
            color="Red",
            grams=1000,
            cost_per_gram=Decimal("0.0200"),
        )
        db.session.add(spool_a)
        db.session.commit()

        # Exact spool for the right business -> high.
        result = resolve_material_cost(biz_a.id, None, spool_id=spool_a.id)
        assert result.cost_per_gram == Decimal("0.0200")
        assert result.confidence == "high"

        # The same spool_id requested under a different business must NOT match
        # that spool; it falls back to business B's (empty) pool -> none.
        leak = resolve_material_cost(biz_b.id, None, spool_id=spool_a.id)
        assert leak.cost_per_gram == Decimal("0.0000")
        assert leak.confidence == "none"
        assert leak.evidence["fallback_reason"] == "no_spools"


# ---------------------------------------------------------------------------
# Issue 25 — confidence logic
# ---------------------------------------------------------------------------


def test_confidence_high_for_exact_material_match(app):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.flush()
        db.session.add(
            _make_spool(
                business_id=biz.id,
                material_type="PLA",
                color="Red",
                grams=1000,
                cost_per_gram=Decimal("0.0200"),
            )
        )
        db.session.commit()

        product = _make_product(
            business_id=biz.id,
            slug="pla",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        db.session.add(product)
        db.session.commit()
        breakdown = calculate_product_cost(product=product)
        assert breakdown.confidence == "high"
        assert breakdown.evidence_source == "generated_slice.product"
        assert breakdown.cost_per_gram == Decimal("0.0200")


def test_failure_rate_does_not_affect_confidence(app):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.flush()
        db.session.add(
            _make_spool(
                business_id=biz.id,
                material_type="PLA",
                color="Red",
                grams=1000,
                cost_per_gram=Decimal("0.0200"),
            )
        )
        db.session.commit()

        product = _make_product(
            business_id=biz.id,
            slug="pla",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        db.session.add(product)
        db.session.commit()

        low_failure = calculate_product_cost(product=product, failure_rate=Decimal("0.01"))
        high_failure = calculate_product_cost(product=product, failure_rate=Decimal("0.95"))
        # Failure rate changes the failure adjustment, not the confidence.
        assert low_failure.confidence == "high"
        assert high_failure.confidence == "high"
        assert high_failure.failure_adjustment > low_failure.failure_adjustment


def test_confidence_none_when_cost_per_gram_zero(app):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.commit()

        product = _make_product(
            business_id=biz.id,
            slug="no-cost",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        db.session.add(product)
        db.session.commit()
        breakdown = calculate_product_cost(product=product)
        assert breakdown.cost_per_gram == Decimal("0.0000")
        assert breakdown.confidence == "none"
        assert breakdown.evidence_source == "no_spool_cost"


def test_cost_resolver_result_dataclass_shape():
    # Sanity-check the public dataclass signature without touching the DB.
    result = CostResolverResult(
        cost_per_gram=Decimal("0.0200"),
        spool_id=7,
        confidence="high",
        evidence={"matched_spool_ids": [7]},
    )
    assert result.cost_per_gram == Decimal("0.0200")
    assert result.spool_id == 7
    assert result.confidence == "high"
    assert result.evidence == {"matched_spool_ids": [7]}


# ---------------------------------------------------------------------------
# Issue 17 — audit hook on snapshot creation
# ---------------------------------------------------------------------------


def test_persist_cost_snapshot_fires_audit_when_client_provided(app, monkeypatch):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.flush()
        db.session.add(
            _make_spool(
                business_id=biz.id,
                material_type="PLA",
                color="Red",
                grams=1000,
                cost_per_gram=Decimal("0.0200"),
            )
        )
        db.session.commit()
        product = _make_product(
            business_id=biz.id,
            slug="audited",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        db.session.add(product)
        db.session.commit()

        breakdown = calculate_product_cost(product=product)

        calls = []

        class FakeAuditClient:
            def record(self, **payload):
                calls.append(payload)
                return {"id": "audit-test"}

        snapshot = persist_cost_snapshot(
            product=product,
            breakdown=breakdown,
            actor_id=42,
            audit_client=FakeAuditClient(),
        )
        db.session.commit()

        assert snapshot.id is not None
        assert any(call["action"] == "cost_snapshot.created" for call in calls)
        created = next(call for call in calls if call["action"] == "cost_snapshot.created")
        assert created["entity_type"] == "cost_snapshot"
        assert created["entity_id"] == str(snapshot.id)
        assert created["actor_id"] == "42"
        assert created["after_state"]["snapshot_id"] == snapshot.id
        assert created["after_state"]["confidence"] == breakdown.confidence


def test_persist_cost_snapshot_swallows_audit_errors(app):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.flush()
        db.session.add(
            _make_spool(
                business_id=biz.id,
                material_type="PLA",
                color="Red",
                grams=1000,
                cost_per_gram=Decimal("0.0200"),
            )
        )
        db.session.commit()
        product = _make_product(
            business_id=biz.id,
            slug="audit-broken",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        db.session.add(product)
        db.session.commit()

        breakdown = calculate_product_cost(product=product)

        class BrokenAuditClient:
            def record(self, **payload):
                raise RuntimeError("audit service down")

        # A failing audit client must not break snapshot creation.
        snapshot = persist_cost_snapshot(
            product=product,
            breakdown=breakdown,
            audit_client=BrokenAuditClient(),
        )
        db.session.commit()
        assert snapshot.id is not None


def test_persist_cost_snapshot_no_audit_when_disabled(app):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.flush()
        db.session.add(
            _make_spool(
                business_id=biz.id,
                material_type="PLA",
                color="Red",
                grams=1000,
                cost_per_gram=Decimal("0.0200"),
            )
        )
        db.session.commit()
        product = _make_product(
            business_id=biz.id,
            slug="no-audit",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        db.session.add(product)
        db.session.commit()

        breakdown = calculate_product_cost(product=product)
        calls = []

        class FakeAuditClient:
            def record(self, **payload):
                calls.append(payload)
                return {"id": "audit-test"}

        # AUDIT_LOG_ENABLED is False in the test config, so even though a client
        # is provided via kwarg it should still fire (explicit client wins);
        # but with no client and the flag off, nothing fires.
        snapshot = persist_cost_snapshot(product=product, breakdown=breakdown)
        db.session.commit()
        assert snapshot.id is not None
        assert calls == []


# ---------------------------------------------------------------------------
# Issue 38 — product-level overrides
# ---------------------------------------------------------------------------


def test_product_level_overrides_apply_when_caller_passes_none(app):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.flush()
        db.session.add(
            _make_spool(
                business_id=biz.id,
                material_type="PLA",
                color="Red",
                grams=1000,
                cost_per_gram=Decimal("0.0200"),
            )
        )
        db.session.commit()
        product = _make_product(
            business_id=biz.id,
            slug="overrides",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        # Attach the override attributes the integrator will add later.
        product.market_allocation_override = Decimal("5.00")
        product.payment_fee_rate_override = Decimal("0.029")
        db.session.add(product)
        db.session.commit()

        breakdown = calculate_product_cost(product=product)
        assert breakdown.market_allocation == Decimal("5.00")
        # payment_fees = price(30) * 0.029 = 0.87
        assert breakdown.payment_fees == Decimal("0.87")


def test_explicit_caller_values_override_product_overrides(app):
    cat_id, col_id = _catalog(app)
    with app.app_context():
        biz = Business(name="A", slug="biz-a")
        db.session.add(biz)
        db.session.flush()
        db.session.add(
            _make_spool(
                business_id=biz.id,
                material_type="PLA",
                color="Red",
                grams=1000,
                cost_per_gram=Decimal("0.0200"),
            )
        )
        db.session.commit()
        product = _make_product(
            business_id=biz.id,
            slug="explicit",
            material="PLA",
            category_id=cat_id,
            collection_id=col_id,
        )
        product.market_allocation_override = Decimal("5.00")
        product.payment_fee_rate_override = Decimal("0.029")
        db.session.add(product)
        db.session.commit()

        breakdown = calculate_product_cost(
            product=product,
            market_allocation=Decimal("1.00"),
            payment_fee_rate=Decimal("0.00"),
        )
        assert breakdown.market_allocation == Decimal("1.00")
        assert breakdown.payment_fees == Decimal("0.00")