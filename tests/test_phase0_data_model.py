from __future__ import annotations

import json
import threading
from decimal import Decimal

from app.extensions import db
from app.models import (
    AnalysisRunStatus,
    AssetKind,
    Category,
    CostSnapshot,
    CostSnapshotConfidence,
    Product,
    ProductModelAsset,
    ProductStatus,
    ProductType,
)
from app.models.catalog import LicenseStatus
from app.services.cost_engine import (
    COST_FORMULA_VERSION,
    calculate_product_cost,
    persist_cost_snapshot,
)
from app.services.product_analysis import (
    ANALYSIS_SUMMARY_FIELDS,
    create_model_asset,
    get_current_run,
    is_current_run,
    publish_run_results,
    reset_product_analysis,
    sanitize_analysis_config,
    start_analysis_run,
)


def _make_product(**overrides) -> Product:
    category = Category(name="Phase0 Cats", slug="phase0-cats", is_public=True)
    data = {
        "name": "Phase0 Dragon",
        "slug": "phase0-dragon",
        "sku_base": "P0-DRAGON",
        "short_description": "A test dragon.",
        "description": "A test dragon.",
        "category": category,
        "product_type": ProductType.FINISHED_GOOD,
        "status": ProductStatus.DRAFT,
        "base_price": 24,
        "estimated_material_cost": 4,
        "license_status": LicenseStatus.COMMERCIAL_ALLOWED,
        "model_commercial_use_allowed": True,
    }
    data.update(overrides)
    product = Product(**data)
    db.session.add(product)
    db.session.flush()
    return product


def _source_asset(product: Product) -> ProductModelAsset:
    return create_model_asset(
        product,
        storage_reference="/uploads/products/source.stl",
        original_filename="source.stl",
        safe_filename="source.stl",
        content_type="model/stl",
        size_bytes=1234,
        sha256="a" * 64,
        asset_kind=AssetKind.SOURCE_MODEL,
    )


# ---------------------------------------------------------------------------
# Issue 6 / 44 — race-proof analysis runs
# ---------------------------------------------------------------------------


def test_starting_a_new_run_supersedes_the_prior_current_run(app):
    with app.app_context():
        product = _make_product()
        asset_a = _source_asset(product)
        run_a = start_analysis_run(product, source_asset=asset_a, requested_by_id=None)
        assert run_a.is_current is True
        assert run_a.status == AnalysisRunStatus.QUEUED

        # A second upload starts a new run; A is superseded.
        asset_b = create_model_asset(
            product,
            storage_reference="/uploads/products/source2.stl",
            original_filename="source2.stl",
            safe_filename="source2.stl",
            content_type="model/stl",
            size_bytes=5678,
            sha256="b" * 64,
            asset_kind=AssetKind.SOURCE_MODEL,
        )
        run_b = start_analysis_run(product, source_asset=asset_b, requested_by_id=None)

        db.session.flush()
        assert run_b.is_current is True
        assert get_current_run(product).id == run_b.id
        assert is_current_run(run_b.id) is True
        assert is_current_run(run_a.id) is False


def test_superseded_run_does_not_overwrite_product_fields(app):
    """Issue 6 step 8: run A completes AFTER run B exists; A must not touch B's product fields."""
    with app.app_context():
        product = _make_product()
        asset = _source_asset(product)
        run_a = start_analysis_run(product, source_asset=asset, requested_by_id=None)

        # Run B arrives and becomes current.
        run_b = start_analysis_run(product, source_asset=asset, requested_by_id=None)
        # B publishes its results to the product first.
        publish_run_results(
            run_b,
            product,
            parsed_filament_grams=Decimal("88.00"),
            parsed_print_minutes=Decimal("120.00"),
        )
        db.session.commit()
        assert product.parsed_filament_grams == Decimal("88.00")
        assert product.analysis_status == "complete"

        # Now the stale run A finishes later and tries to publish.
        published = publish_run_results(
            run_a,
            product,
            parsed_filament_grams=Decimal("999.00"),
            parsed_print_minutes=Decimal("999.00"),
        )
        db.session.commit()

        assert published is False
        assert run_a.status == AnalysisRunStatus.SUPERSEDED
        # Product fields still reflect B, untouched by A.
        assert product.parsed_filament_grams == Decimal("88.00")
        assert product.parsed_print_minutes == Decimal("120.00")
        assert product.analysis_status == "complete"


# ---------------------------------------------------------------------------
# Issue 7 — current vs stale assets
# ---------------------------------------------------------------------------


def test_new_source_model_marks_prior_source_stale(app):
    with app.app_context():
        product = _make_product()
        first = _source_asset(product)
        assert first.is_current is True
        second = _source_asset(product)
        db.session.flush()
        db.session.refresh(first)
        assert first.is_current is False
        assert second.is_current is True


def test_new_gcode_marks_only_prior_gcode_stale(app):
    with app.app_context():
        product = _make_product()
        source = _source_asset(product)
        first = create_model_asset(
            product,
            storage_reference="/uploads/products/first.gcode",
            original_filename="first.gcode",
            safe_filename="first.gcode",
            content_type="text/x.gcode",
            size_bytes=12,
            sha256="b" * 64,
            asset_kind=AssetKind.GCODE,
        )
        second = create_model_asset(
            product,
            storage_reference="/uploads/products/second.gcode.3mf",
            original_filename="second.gcode.3mf",
            safe_filename="second.gcode.3mf",
            content_type="application/vnd.bambulab.gcode-3mf",
            size_bytes=34,
            sha256="c" * 64,
            asset_kind=AssetKind.GCODE,
        )

        db.session.flush()
        db.session.refresh(source)
        db.session.refresh(first)

        assert source.is_current is True
        assert first.is_current is False
        assert second.is_current is True


def test_completed_run_points_to_generated_gcode_asset(app):
    with app.app_context():
        product = _make_product()
        source = _source_asset(product)
        run = start_analysis_run(product, source_asset=source)
        artifact = create_model_asset(
            product,
            storage_reference="/uploads/products/dragon.gcode.3mf",
            original_filename="dragon.gcode.3mf",
            safe_filename="dragon.gcode.3mf",
            content_type="application/vnd.bambulab.gcode-3mf",
            size_bytes=9876,
            sha256="d" * 64,
            asset_kind=AssetKind.GCODE,
        )

        published = publish_run_results(
            run,
            product,
            slicer_stats={"engine_key": "bambu"},
            gcode_asset_id=artifact.id,
        )
        db.session.commit()

        assert published is True
        assert run.status == AnalysisRunStatus.COMPLETE
        assert run.gcode_asset_id == artifact.id
        assert run.gcode_asset.content_type == "application/vnd.bambulab.gcode-3mf"
        assert run.gcode_asset.size_bytes == 9876
        assert run.gcode_asset.sha256 == "d" * 64


def test_reset_product_analysis_clears_stale_cost_fields(app):
    """Issue 27 helper: re-analyze clears stale numbers."""
    with app.app_context():
        product = _make_product(
            analysis_status="complete",
            parsed_filament_grams=Decimal("50"),
            parsed_print_minutes=Decimal("90"),
            estimated_material_cost=Decimal("3"),
            estimated_profit=Decimal("20"),
            gcode_path="/uploads/x.gcode",
        )
        reset_product_analysis(product)
        assert product.analysis_status == "pending"
        for field in ANALYSIS_SUMMARY_FIELDS:
            assert getattr(product, field) is None


# ---------------------------------------------------------------------------
# Issue 40 — bounded model_analysis_config
# ---------------------------------------------------------------------------


def test_sanitize_analysis_config_strips_large_blob_keys():
    raw = {
        "material": "PLA",
        "filament_density": "1.24",
        "slicer_results": {"grams": 12},  # large blob — must be removed
        "geometry": {"width_mm": 30},  # large blob — must be removed
        "embedded_settings_detected": {"a": 1},  # must be removed
        "copies": 3,
        "rogue_key": "evil",
    }
    cleaned = sanitize_analysis_config(raw)
    assert "slicer_results" not in cleaned
    assert "geometry" not in cleaned
    assert "embedded_settings_detected" not in cleaned
    assert "rogue_key" not in cleaned
    assert cleaned["material"] == "PLA"
    assert cleaned["copies"] == 3


def test_sanitize_analysis_config_empty():
    assert sanitize_analysis_config(None) == {}
    assert sanitize_analysis_config({}) == {}


# ---------------------------------------------------------------------------
# Issue 15 / 46 — cost snapshot evidence
# ---------------------------------------------------------------------------


def _analyzed_product() -> Product:
    product = _make_product()
    product.analysis_status = "complete"
    product.parsed_filament_grams = Decimal("42.00")
    product.parsed_print_minutes = Decimal("60.00")
    product.parsed_volume_mm3 = Decimal("8000.0000")
    db.session.flush()
    return product


def test_cost_snapshot_records_full_evidence(app):
    with app.app_context():
        product = _analyzed_product()
        asset = _source_asset(product)
        run = start_analysis_run(product, source_asset=asset, requested_by_id=None)
        breakdown = calculate_product_cost(product=product)
        snapshot = persist_cost_snapshot(
            product=product,
            breakdown=breakdown,
            snapshot_reason="test",
            analysis_run_id=run.id,
            model_asset_id=asset.id,
            file_sha256=asset.sha256,
            slicer_settings_hash="settingshash",
            material="PLA",
            density=Decimal("1.24"),
            density_source="default",
            scale_percent=100,
            copies=1,
            cost_resolver_evidence={"matched_spool": 7},
        )
        db.session.commit()
        assert snapshot.model_asset_id == asset.id
        assert snapshot.analysis_run_id == run.id
        assert snapshot.file_sha256 == asset.sha256
        assert snapshot.slicer_settings_hash == "settingshash"
        assert snapshot.material == "PLA"
        assert snapshot.density == Decimal("1.24")
        assert snapshot.density_source == "default"
        assert snapshot.scale_percent == 100
        assert snapshot.copies == 1
        assert snapshot.formula_version == "1.0.0"
        assert snapshot.parsed_filament_grams == Decimal("42.00")
        evidence = json.loads(snapshot.cost_resolver_evidence_json)
        assert evidence["matched_spool"] == 7


# ---------------------------------------------------------------------------
# Issue 26 — one current snapshot per product under concurrency
# ---------------------------------------------------------------------------


def test_new_snapshot_marks_prior_stale(app):
    with app.app_context():
        product = _analyzed_product()
        breakdown = calculate_product_cost(product=product)
        first = persist_cost_snapshot(product=product, breakdown=breakdown, snapshot_reason="one")
        db.session.commit()
        second = persist_cost_snapshot(product=product, breakdown=breakdown, snapshot_reason="two")
        db.session.commit()
        db.session.refresh(first)
        assert first.stale is True
        assert second.stale is False
        current = [s for s in product.cost_snapshots if not s.stale]
        assert len(current) == 1


def test_concurrent_cost_snapshots_leave_single_current(app):
    """Two threads create snapshots for the same product; the FOR UPDATE lock
    serializes them so exactly one ends up current (Issue 26)."""
    with app.app_context():
        product = _analyzed_product()
        product_id = product.id
        db.session.commit()

    results: list[int | None] = [None, None]
    barrier = threading.Barrier(2)

    def worker(index: int) -> None:
        app_ctx = app.app_context()
        app_ctx.push()
        try:
            barrier.wait()
            prod = db.session.get(Product, product_id)
            breakdown = calculate_product_cost(product=prod)
            snapshot = persist_cost_snapshot(
                product=prod, breakdown=breakdown, snapshot_reason=f"thread-{index}"
            )
            db.session.commit()
            results[index] = snapshot.id
        finally:
            db.session.remove()
            app_ctx.pop()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(r is not None for r in results), f"workers did not finish: {results}"

    with app.app_context():
        current = (
            db.session.query(CostSnapshot)
            .filter(
                CostSnapshot.product_id == product_id,
                CostSnapshot.stale.is_(False),
            )
            .all()
        )
        assert len(current) == 1, (
            "concurrent cost calculations produced more than one current snapshot"
        )


# ---------------------------------------------------------------------------
# Issue 43 — semantic cost formula version
# ---------------------------------------------------------------------------


def test_cost_formula_version_is_semantic():
    parts = COST_FORMULA_VERSION.split(".")
    assert len(parts) == 3, f"expected MAJOR.MINOR.PATCH, got {COST_FORMULA_VERSION}"
    for part in parts:
        assert part.isdigit(), f"non-numeric version segment: {part}"


def test_calculate_product_cost_sets_semver_in_breakdown(app):
    with app.app_context():
        product = _analyzed_product()
        breakdown = calculate_product_cost(product=product)
        assert breakdown.formula_version == "1.0.0"
        assert breakdown.confidence in {
            CostSnapshotConfidence.NONE,
            CostSnapshotConfidence.LOW,
            CostSnapshotConfidence.MEDIUM,
            CostSnapshotConfidence.HIGH,
        }
