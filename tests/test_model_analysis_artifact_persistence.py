from __future__ import annotations

import hashlib
import threading
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

from app.extensions import db
from app.models import (
    AnalysisRunStatus,
    AssetKind,
    Category,
    Product,
    ProductAnalysisRun,
    ProductModelAsset,
    ProductStatus,
    ProductType,
)
from app.services.model_analysis import SlicerResult, ValidationResult
from app.services.product_analysis import (
    create_model_asset,
    lock_product_for_analysis,
    start_analysis_run,
)
from app.tasks import model_analysis as analysis_task


class _AuditRecorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _product_with_run(tmp_path: Path, *, retain_gcode: bool = True) -> tuple[int, int]:
    source_path = tmp_path / "dragon.stl"
    source_path.write_bytes(b"solid dragon\nendsolid dragon\n")
    category = Category(name="Artifacts", slug="artifacts", is_public=True)
    product = Product(
        name="Artifact Dragon",
        slug="artifact-dragon",
        sku_base="ART-DRAGON",
        category=category,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.DRAFT,
        base_price=Decimal("20.00"),
        model_file_path=str(source_path),
        model_convert_to_glb=False,
        model_analysis_config={
            "printer_profile": "bambu_a1",
            "material": "PLA",
            "copies": 2,
            "retain_gcode": retain_gcode,
        },
    )
    db.session.add_all([category, product])
    db.session.flush()
    source = create_model_asset(
        product,
        storage_reference=str(source_path),
        original_filename="dragon.stl",
        safe_filename="dragon.stl",
        content_type="model/stl",
        size_bytes=source_path.stat().st_size,
        sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        asset_kind=AssetKind.SOURCE_MODEL,
    )
    run = start_analysis_run(
        product,
        source_asset=source,
        settings=dict(product.model_analysis_config or {}),
    )
    db.session.commit()
    return product.id, run.id


def _bambu_result(workspace: str | Path) -> SlicerResult:
    artifact = Path(workspace) / "artifact-dragon.gcode.3mf"
    artifact.write_bytes(b"native-bambu-package")
    return SlicerResult(
        filament_grams=Decimal("12.50"),
        print_minutes=Decimal("45.25"),
        profile_used="bambu_a1.ini",
        artifact_path=artifact,
        artifact_filename=artifact.name,
        artifact_media_type="application/vnd.bambulab.gcode-3mf",
        artifact_size=artifact.stat().st_size,
        artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        engine_key="bambu",
        engine_name="Bambu Studio",
        engine_version="2.7.1.62",
        fallback_used=False,
        direct_print_eligible=True,
        estimate_only=False,
        success=True,
        stats={
            "layer_count": 123,
            "profile_ids": {
                "machine": "Bambu Lab A1 0.4 nozzle",
                "process": "0.20mm Standard @BBL A1",
                "filament": "Generic PLA @BBL A1",
            },
            "primary_failure": None,
        },
    )


def _prusa_fallback_result(workspace: str | Path) -> SlicerResult:
    artifact = Path(workspace) / "artifact-dragon.gcode"
    artifact.write_bytes(b"; native prusa gcode")
    return SlicerResult(
        filament_grams=Decimal("8.25"),
        print_minutes=Decimal("30.5"),
        profile_used="bambu_a1.ini",
        artifact_path=artifact,
        artifact_filename=artifact.name,
        artifact_media_type="text/x.gcode",
        artifact_size=artifact.stat().st_size,
        artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        engine_key="prusa",
        engine_name="PrusaSlicer",
        engine_version="2.9.2",
        fallback_used=True,
        direct_print_eligible=False,
        estimate_only=True,
        success=True,
        stats={
            "layer_count": 99,
            "profile_ids": {"printer": "bambu_a1"},
            "primary_failure": {
                "engine_key": "bambu",
                "code": "execution_failed",
                "message": "Bambu Studio execution failed.",
            },
        },
    )


def _run_analysis(monkeypatch, product_id: int, run_id: int, result_factory):
    recorder = _AuditRecorder()
    slicer_call = Mock(side_effect=lambda *args, **kwargs: result_factory(kwargs["workspace"]))
    snapshot = Mock()
    monkeypatch.setattr(analysis_task, "get_audit_client", lambda: recorder)
    monkeypatch.setattr(analysis_task, "slice_with_slicer", slicer_call, raising=False)
    monkeypatch.setattr(
        analysis_task,
        "validate_model_file",
        lambda path: ValidationResult(
            success=True,
            volume_mm3=1000,
            surface_area_mm2=600,
            triangle_count=12,
            is_watertight=True,
            printer_fit=True,
            bounding_box={"width_mm": 10, "depth_mm": 10, "height_mm": 10},
            format_detected=".stl",
        ),
    )
    monkeypatch.setattr(analysis_task, "extract_3mf_slicer_settings", lambda path: {})
    monkeypatch.setattr(
        analysis_task, "_resolve_material_cost", lambda *args: (Decimal("0.02"), None, {})
    )
    monkeypatch.setattr(analysis_task, "_apply_initial_cost_snapshot", snapshot)
    monkeypatch.setattr(analysis_task, "write_model_metadata", lambda product: None)
    monkeypatch.setattr(analysis_task, "_record_analysis_step", lambda *args, **kwargs: None)

    result = analysis_task.analyze_product_model.run(product_id, run_id)
    return result, recorder, slicer_call, snapshot


def test_analysis_persists_native_bambu_artifact_before_workspace_cleanup(
    app, tmp_path, monkeypatch
):
    with app.app_context():
        product_id, run_id = _product_with_run(tmp_path)
        result, recorder, slicer_call, snapshot = _run_analysis(
            monkeypatch, product_id, run_id, _bambu_result
        )

        run = db.session.get(ProductAnalysisRun, run_id)
        product = db.session.get(Product, product_id)
        assets = ProductModelAsset.query.filter_by(
            product_id=product_id, asset_kind=AssetKind.GCODE
        ).all()

        assert result["success"] is True
        assert slicer_call.call_count == 1
        assert slicer_call.call_args.kwargs["workspace"]
        assert Path(slicer_call.call_args.kwargs["workspace"]).exists() is False
        assert snapshot.call_count == 1
        assert run.status == AnalysisRunStatus.COMPLETE
        assert len(assets) == 1
        artifact = assets[0]
        assert run.gcode_asset_id == artifact.id
        assert product.gcode_path == artifact.storage_reference
        assert artifact.safe_filename == "artifact-dragon.gcode.3mf"
        assert artifact.content_type == "application/vnd.bambulab.gcode-3mf"
        assert artifact.size_bytes == len(b"native-bambu-package")
        assert artifact.sha256 == hashlib.sha256(b"native-bambu-package").hexdigest()
        assert Path(artifact.storage_reference).read_bytes() == b"native-bambu-package"
        assert run.slicer_stats_json["engine_key"] == "bambu"
        assert run.slicer_stats_json["engine_version"] == "2.7.1.62"
        assert run.slicer_stats_json["fallback_used"] is False
        assert run.slicer_stats_json["direct_print_eligible"] is True
        assert run.slicer_stats_json["estimate_only"] is False
        assert run.slicer_stats_json["artifact_filename"] == artifact.safe_filename
        assert run.slicer_stats_json["artifact_media_type"] == artifact.content_type
        assert run.slicer_stats_json["artifact_size"] == artifact.size_bytes
        assert run.slicer_stats_json["artifact_sha256"] == artifact.sha256
        assert run.slicer_stats_json["profile_ids"]["machine"] == "Bambu Lab A1 0.4 nozzle"
        assert run.slicer_stats_json["copies"] == 2
        assert run.slicer_stats_json["plate_cost"] == "0.50"
        completed = [
            call for call in recorder.calls if call["action"] == "model_analysis.completed"
        ]
        assert completed[0]["metadata"] == {
            "percent": 100,
            "conversion_queued": False,
            "outcome": "success",
            "engine_key": "bambu",
            "fallback_used": False,
            "estimate_only": False,
            "artifact_sha256": artifact.sha256,
        }


def test_analysis_retains_fallback_metadata_without_artifact_when_disabled(
    app, tmp_path, monkeypatch
):
    with app.app_context():
        product_id, run_id = _product_with_run(tmp_path, retain_gcode=False)
        product = db.session.get(Product, product_id)
        previous_gcode = create_model_asset(
            product,
            storage_reference=str(tmp_path / "previous.gcode.3mf"),
            original_filename="previous.gcode.3mf",
            safe_filename="previous.gcode.3mf",
            content_type="application/vnd.bambulab.gcode-3mf",
            size_bytes=8,
            sha256="e" * 64,
            asset_kind=AssetKind.GCODE,
        )
        product.gcode_path = previous_gcode.storage_reference
        db.session.commit()
        result, _, slicer_call, snapshot = _run_analysis(
            monkeypatch, product_id, run_id, _prusa_fallback_result
        )

        run = db.session.get(ProductAnalysisRun, run_id)
        product = db.session.get(Product, product_id)

        assert result["success"] is True
        assert slicer_call.call_count == 1
        assert snapshot.call_count == 1
        assert run.gcode_asset_id is None
        assert product.gcode_path is None
        db.session.refresh(previous_gcode)
        source = ProductModelAsset.query.filter_by(
            product_id=product_id,
            asset_kind=AssetKind.SOURCE_MODEL,
        ).one()
        assert previous_gcode.is_current is False
        assert source.is_current is True
        assert (
            ProductModelAsset.query.filter_by(
                product_id=product_id,
                asset_kind=AssetKind.GCODE,
            ).count()
            == 1
        )
        assert run.slicer_stats_json["engine_key"] == "prusa"
        assert run.slicer_stats_json["fallback_used"] is True
        assert run.slicer_stats_json["estimate_only"] is True
        assert run.slicer_stats_json["direct_print_eligible"] is False
        assert run.slicer_stats_json["primary_failure"] == {
            "engine_key": "bambu",
            "code": "execution_failed",
            "message": "Bambu Studio execution failed.",
        }
        assert run.slicer_stats_json["artifact_filename"] == "artifact-dragon.gcode"
        assert run.slicer_stats_json["artifact_media_type"] == "text/x.gcode"
        assert (
            run.slicer_stats_json["artifact_sha256"]
            == hashlib.sha256(b"; native prusa gcode").hexdigest()
        )


def test_worker_uses_exact_run_source_and_settings_snapshot(app, tmp_path, monkeypatch):
    with app.app_context():
        product_id, run_id = _product_with_run(tmp_path)
        product = db.session.get(Product, product_id)
        newer_path = tmp_path / "newer-product-pointer.stl"
        newer_path.write_bytes(b"not the claimed run source")
        product.model_file_path = str(newer_path)
        product.model_analysis_config = {"material": "ABS", "copies": 9}
        db.session.commit()

        result, _, slicer_call, _ = _run_analysis(monkeypatch, product_id, run_id, _bambu_result)

        assert result["success"] is True
        assert slicer_call.call_args.args[0] == tmp_path / "dragon.stl"
        assert slicer_call.call_args.kwargs["slicer_options"]["material"] == "PLA"
        assert slicer_call.call_args.kwargs["slicer_options"]["copies"] == 2


def test_duplicate_delivery_does_not_slice_publish_or_create_another_asset(
    app, tmp_path, monkeypatch
):
    with app.app_context():
        product_id, run_id = _product_with_run(tmp_path)
        first, _, first_slice, first_snapshot = _run_analysis(
            monkeypatch, product_id, run_id, _bambu_result
        )
        asset = ProductModelAsset.query.filter_by(
            product_id=product_id, asset_kind=AssetKind.GCODE
        ).one()
        first_reference = asset.storage_reference

        second, second_audit, second_slice, second_snapshot = _run_analysis(
            monkeypatch, product_id, run_id, _bambu_result
        )

        assert first["success"] is True
        assert first_slice.call_count == 1
        assert first_snapshot.call_count == 1
        assert second == {
            "success": False,
            "data": {"product_id": product_id, "run_id": run_id, "idempotent": True},
            "error": "analysis run is not claimable",
        }
        assert second_slice.call_count == 0
        assert second_snapshot.call_count == 0
        assert second_audit.calls == []
        assert (
            ProductModelAsset.query.filter_by(
                product_id=product_id, asset_kind=AssetKind.GCODE
            ).count()
            == 1
        )
        assert Path(first_reference).read_bytes() == b"native-bambu-package"


def test_two_uploads_queued_before_workers_do_not_redirect_old_task_to_new_run(
    app, tmp_path, monkeypatch
):
    with app.app_context():
        product_id, first_run_id = _product_with_run(tmp_path)
        product = db.session.get(Product, product_id)
        source = ProductModelAsset.query.filter_by(
            product_id=product_id, asset_kind=AssetKind.SOURCE_MODEL, is_current=True
        ).one()
        second_run = start_analysis_run(
            product,
            source_asset=source,
            settings={"printer_profile": "bambu_p1p", "material": "PETG", "copies": 1},
        )
        db.session.commit()

        stale_result, stale_audit, stale_slice, stale_snapshot = _run_analysis(
            monkeypatch, product_id, first_run_id, _bambu_result
        )

        assert stale_result["data"]["idempotent"] is True
        assert stale_slice.call_count == 0
        assert stale_snapshot.call_count == 0
        assert stale_audit.calls == []
        assert db.session.get(ProductAnalysisRun, first_run_id).status == (
            AnalysisRunStatus.SUPERSEDED
        )
        assert db.session.get(ProductAnalysisRun, second_run.id).status == AnalysisRunStatus.QUEUED


def test_two_runs_with_same_native_filename_keep_distinct_references_and_bytes(
    app, tmp_path, monkeypatch
):
    with app.app_context():
        product_id, first_run_id = _product_with_run(tmp_path)
        first, _, _, _ = _run_analysis(monkeypatch, product_id, first_run_id, _bambu_result)
        assert first["success"] is True
        first_asset = ProductModelAsset.query.filter_by(
            product_id=product_id, asset_kind=AssetKind.GCODE, is_current=True
        ).one()
        first_reference = first_asset.storage_reference

        product = db.session.get(Product, product_id)
        source = ProductModelAsset.query.filter_by(
            product_id=product_id, asset_kind=AssetKind.SOURCE_MODEL, is_current=True
        ).one()
        second_run = start_analysis_run(
            product,
            source_asset=source,
            settings={"printer_profile": "bambu_a1", "material": "PLA", "copies": 2},
        )
        db.session.commit()

        def changed_bambu_result(workspace):
            result = _bambu_result(workspace)
            payload = b"new-native-bambu-package"
            result.artifact_path.write_bytes(payload)
            result.artifact_size = len(payload)
            result.artifact_sha256 = hashlib.sha256(payload).hexdigest()
            return result

        second, _, _, _ = _run_analysis(
            monkeypatch, product_id, second_run.id, changed_bambu_result
        )

        db.session.refresh(first_asset)
        second_asset = ProductModelAsset.query.filter_by(
            product_id=product_id, asset_kind=AssetKind.GCODE, is_current=True
        ).one()
        assert second["success"] is True
        assert first_asset.is_current is False
        assert first_reference != second_asset.storage_reference
        assert f"/analysis-runs/{first_run_id}/" in first_reference
        assert f"/analysis-runs/{second_run.id}/" in second_asset.storage_reference
        assert Path(first_reference).read_bytes() == b"native-bambu-package"
        assert Path(second_asset.storage_reference).read_bytes() == b"new-native-bambu-package"


def test_concurrent_uploads_serialize_source_and_run_as_one_locked_transaction(app, tmp_path):
    with app.app_context():
        product_id, _ = _product_with_run(tmp_path)

    first_locked = threading.Event()
    second_attempting = threading.Event()
    first_committed = threading.Event()
    second_acquired = threading.Event()
    errors: list[BaseException] = []

    def upload(index: int) -> None:
        with app.app_context():
            try:
                if index == 2:
                    assert first_locked.wait(timeout=10)
                    second_attempting.set()
                product = lock_product_for_analysis(product_id)
                assert product is not None
                if index == 1:
                    first_locked.set()
                    assert second_attempting.wait(timeout=10)
                    assert second_acquired.is_set() is False
                else:
                    second_acquired.set()
                    assert first_committed.is_set() is True
                payload = f"source-{index}".encode()
                source = create_model_asset(
                    product,
                    storage_reference=str(tmp_path / f"source-{index}.stl"),
                    original_filename=f"source-{index}.stl",
                    safe_filename=f"source-{index}.stl",
                    content_type="model/stl",
                    size_bytes=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    asset_kind=AssetKind.SOURCE_MODEL,
                )
                start_analysis_run(
                    product,
                    source_asset=source,
                    settings={"material": "PLA", "copies": index},
                    product_locked=True,
                )
                db.session.commit()
                if index == 1:
                    first_committed.set()
            except BaseException as exc:  # pragma: no cover - surfaced below
                db.session.rollback()
                errors.append(exc)
                first_committed.set()
            finally:
                db.session.remove()

    first = threading.Thread(target=upload, args=(1,))
    second = threading.Thread(target=upload, args=(2,))
    first.start()
    second.start()
    first.join(timeout=20)
    second.join(timeout=20)

    assert first.is_alive() is False
    assert second.is_alive() is False
    assert errors == []
    with app.app_context():
        current_source = ProductModelAsset.query.filter_by(
            product_id=product_id,
            asset_kind=AssetKind.SOURCE_MODEL,
            is_current=True,
        ).one()
        current_run = ProductAnalysisRun.query.filter_by(
            product_id=product_id,
            is_current=True,
        ).one()
        assert current_run.source_asset_id == current_source.id
        assert current_run.settings_json["copies"] == 2
