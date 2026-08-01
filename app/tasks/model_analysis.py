from __future__ import annotations

import shutil
import tempfile
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from flask import current_app

from app.celery_app import celery
from app.extensions import db
from app.models.catalog import (
    AnalysisRunStatus,
    AssetKind,
    Product,
    ProductAnalysisRun,
    ProductModelAsset,
)
from app.services.cost_engine import calculate_product_cost, persist_cost_snapshot
from app.services.audit_client import get_audit_client
from app.services.model_asset_metadata import write_model_metadata
from app.services.model_analysis import (
    PRINTER_BUILD_VOLUMES,
    apply_scale,
    convert_to_glb,
    extract_3mf_slicer_settings,
    is_quotable_format,
    normalize_scale_percent,
    slice_with_slicer,
    task_envelope,
    validate_model_file,
)
from app.services.product_analysis import (
    claim_analysis_run,
    create_model_asset,
    lock_current_analysis_run_for_publish,
    publish_run_results,
    requeue_analysis_run,
    sanitize_analysis_config,
    set_run_status,
)
from app.services.materials import material_default_temp, resolve_density
from app.services.storage import (
    converted_storage_key,
    delete_storage_reference,
    download_storage_bytes,
    gcode_storage_key,
    is_s3_reference,
    normalize_storage_filename,
    planned_storage_reference,
    product_storage_key,
    storage_reference_name,
    storage_slug,
    upload_bytes_to_storage,
    upload_file_to_storage,
)


logger = logging.getLogger(__name__)


@dataclass
class _ArtifactPublicationState:
    storage_reference: str | None = None
    artifact_size: int | None = None
    artifact_sha256: str | None = None
    commit_attempted: bool = False
    committed: bool = False


def _artifact_reference_committed(
    *,
    storage_reference: str,
    run_id: int,
    artifact_size: int | None,
    artifact_sha256: str | None,
    session=None,
) -> bool:
    """Check a possibly ambiguous commit using the caller's fresh session."""
    session = session or db.session
    run = session.get(ProductAnalysisRun, run_id)
    artifact = (
        session.get(ProductModelAsset, run.gcode_asset_id)
        if run is not None and run.gcode_asset_id is not None
        else None
    )
    return bool(
        artifact
        and run
        and run.gcode_asset_id == artifact.id
        and artifact.storage_reference == storage_reference
        and artifact.size_bytes == artifact_size
        and artifact.sha256 == artifact_sha256
        and artifact.asset_kind == AssetKind.GCODE
    )


def _mark_run_failed_fresh(*, product_id: int, run_id: int, error: str) -> None:
    """Mark the exact claimed run failed in a clean transaction when safe."""
    run = db.session.get(ProductAnalysisRun, run_id)
    if (
        run is None
        or run.product_id != product_id
        or run.status
        in {
            AnalysisRunStatus.COMPLETE,
            AnalysisRunStatus.FAILED,
            AnalysisRunStatus.SUPERSEDED,
        }
    ):
        return

    run.status = AnalysisRunStatus.FAILED
    run.error = error
    run.completed_at = datetime.now(timezone.utc)
    db.session.add(run)
    if run.is_current:
        product = db.session.get(Product, product_id)
        if product is not None:
            product.analysis_status = "failed"
            product.analysis_error = error
            db.session.add(product)
    db.session.commit()


def _recover_failed_publication(
    state: _ArtifactPublicationState,
    *,
    product_id: int,
    run_id: int,
    original_error: Exception,
    session=None,
    delete_reference=None,
    committed_check=None,
    mark_failed=None,
) -> None:
    """Rollback failed publication and compensate its unique uploaded object.

    A failed commit has an ambiguous outcome, so the exact asset/run link is
    checked through a fresh scoped session before deletion. Recovery failures
    are logged and never replace ``original_error``.
    """
    session = session or db.session
    delete_reference = delete_reference or delete_storage_reference
    committed_check = committed_check or _artifact_reference_committed
    mark_failed = mark_failed or _mark_run_failed_fresh
    original_exc_info = (type(original_error), original_error, original_error.__traceback__)

    try:
        session.rollback()
    except Exception:
        logger.error("analysis publication rollback failed", exc_info=original_exc_info)

    if state.committed:
        return

    committed = False
    if state.storage_reference and state.commit_attempted:
        try:
            session.remove()
            committed = bool(
                committed_check(
                    storage_reference=state.storage_reference,
                    run_id=run_id,
                    artifact_size=state.artifact_size,
                    artifact_sha256=state.artifact_sha256,
                )
            )
        except Exception:
            logger.error(
                "analysis publication commit outcome could not be verified",
                exc_info=original_exc_info,
            )
            # An unknown outcome must fail closed against object deletion.
            committed = True

    if committed:
        return

    if state.storage_reference:
        try:
            delete_reference(state.storage_reference)
        except Exception:
            logger.error(
                "uncommitted slicer artifact cleanup failed",
                exc_info=original_exc_info,
            )

    try:
        session.remove()
        mark_failed(
            product_id=product_id,
            run_id=run_id,
            error=str(original_error),
        )
    except Exception:
        logger.error(
            "fresh analysis failure publication failed",
            exc_info=original_exc_info,
        )


def _record_pmp_step(
    task, product: Product, actor_id: int | None, *, step: str, percent: int, message: str
) -> None:
    task.update_state(state="PROGRESS", meta={"step": step, "percent": percent, "message": message})
    get_audit_client().record(
        action=f"product_model.pmp.{step}",
        entity_type="product",
        entity_id=str(product.id),
        actor_id=str(actor_id) if actor_id else None,
        actor_type="user" if actor_id else "system",
        source_module="app.tasks.model_analysis",
        tenant_id=str(product.business_id) if product.business_id else None,
        metadata={"percent": percent, "message": message},
    )


@celery.task(bind=True)
def pack_product_model(
    self,
    product_id: int,
    source_reference: str,
    source_name: str,
    actor_id: int | None = None,
    printer_profile: str | None = None,
) -> dict:
    """Run PMP for one verified product asset and store its generated artifacts."""
    product = db.session.get(Product, product_id)
    if product is None:
        return task_envelope(False, error="Product not found")
    out_path: Path | None = None
    try:
        _record_pmp_step(
            self, product, actor_id, step="started", percent=5, message="PMP packing started"
        )
        source_bytes = download_storage_bytes(source_reference)
        _record_pmp_step(
            self,
            product,
            actor_id,
            step="downloaded",
            percent=20,
            message="Source model downloaded",
        )

        from pmp import pack_model_bytes

        # Issue 37 — derive the printer profile and bed dimensions from the
        # product config instead of hardcoding "u1". The bed gets a small margin
        # so PMP does not place parts flush against the edge.
        profile = (
            printer_profile
            or (product.model_analysis_config or {}).get("printer_profile")
            or "bambu_a1"
        )
        profile_stem = Path(str(profile)).stem
        build_vol = PRINTER_BUILD_VOLUMES.get(profile_stem, PRINTER_BUILD_VOLUMES["bambu_a1"])
        bed_w = float(build_vol["x"]) + 14.0
        bed_d = float(build_vol["y"]) + 14.0

        result = pack_model_bytes(
            source_bytes,
            source_name,
            target=None,
            spacing=2.0,
            bed_w=bed_w,
            bed_d=bed_d,
            count=None,
            angle_step=15.0,
            pack_mode="auto",
            tower="auto",
            margin=3.5,
            printer=profile_stem,
        )
        out_path = Path(result["out_path"])
        _record_pmp_step(
            self,
            product,
            actor_id,
            step="packed",
            percent=75,
            message=f"PMP placed {result['placed']} copies",
        )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        stem = normalize_storage_filename(Path(source_name).stem).rsplit(".", 1)[0]
        output_name = f"{stem}__packed-plate__{timestamp}-{uuid.uuid4().hex[:6]}.3mf"
        output_bytes = out_path.read_bytes()
        bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
        local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
        output_ref = upload_bytes_to_storage(
            output_bytes,
            bucket=bucket,
            key=product_storage_key(product.id, output_name),
            local_root=local_root,
            content_type="application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        )
        metadata = {
            "schema": "dfpos.pmp-packed-plate",
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "product": {"id": product.id, "name": product.name, "sku": product.sku_base},
            "source": {
                "filename": source_name,
                "reference": source_reference,
                "size_bytes": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "format": result["source_format"],
            },
            "pmp": {
                "bed_width_mm": bed_w,
                "bed_depth_mm": bed_d,
                "spacing_mm": 2.0,
                "margin_mm": 3.5,
                "angle_step_degrees": 15.0,
                "mode": "auto",
                "tower": "auto",
                "printer_profile": profile_stem,
                "scale": result["scale"],
                "placed": result["placed"],
                "method": result["method"],
                "bed_utilization": result["utilization"],
                "usable_utilization": result["usable_utilization"],
                "warnings": result["warnings"],
                "reserved_area": result["reserve"],
            },
            "output": {
                "filename": output_name,
                "reference": output_ref,
                "size_bytes": len(output_bytes),
                "sha256": hashlib.sha256(output_bytes).hexdigest(),
            },
            "generated_by": actor_id,
        }
        metadata_name = f"{Path(output_name).stem}.metadata.json"
        metadata_ref = upload_bytes_to_storage(
            json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8"),
            bucket=bucket,
            key=product_storage_key(product.id, metadata_name),
            local_root=local_root,
            content_type="application/json",
        )
        _record_pmp_step(
            self,
            product,
            actor_id,
            step="stored",
            percent=95,
            message="Packed plate and metadata saved",
        )
        get_audit_client().record(
            action="product_model.pmp.completed",
            entity_type="product",
            entity_id=str(product.id),
            actor_id=str(actor_id) if actor_id else None,
            actor_type="user" if actor_id else "system",
            source_module="app.tasks.model_analysis",
            tenant_id=str(product.business_id) if product.business_id else None,
            after_state={"packed_model": output_ref, "metadata": metadata_ref},
            metadata={"percent": 100, "placed": result["placed"], "method": result["method"]},
        )
        return task_envelope(
            True,
            data={
                "filename": output_name,
                "reference": output_ref,
                "metadata_reference": metadata_ref,
                "placed": result["placed"],
                "printer_profile": profile_stem,
            },
        )
    except Exception as exc:
        get_audit_client().record(
            action="product_model.pmp.failed",
            entity_type="product",
            entity_id=str(product.id),
            actor_id=str(actor_id) if actor_id else None,
            actor_type="user" if actor_id else "system",
            source_module="app.tasks.model_analysis",
            tenant_id=str(product.business_id) if product.business_id else None,
            metadata={"error": str(exc)},
        )
        raise
    finally:
        if out_path is not None:
            shutil.rmtree(out_path.parent, ignore_errors=True)


def _preferred_gcode_filename(product: Product, engine_key: str) -> str:
    label = product.slug or product.name or f"product-{product.id or 0}"
    suffix = ".gcode.3mf" if engine_key == "bambu" else ".gcode"
    return f"{storage_slug(label, fallback=f'product-{product.id or 0}')}{suffix}"


def _preferred_converted_filename(product: Product) -> str:
    source_name = storage_reference_name(product.model_file_path)
    source_stem = Path(source_name).stem if source_name else f"product-{product.id or 0}"
    return normalize_storage_filename(f"{source_stem}.glb")


def _persist_slicer_artifact(
    product: Product,
    run: ProductAnalysisRun,
    slicer_result,
    publication: _ArtifactPublicationState,
    *,
    bucket: str,
    local_root: str | Path,
    upload=None,
    create_asset=None,
) -> tuple[ProductModelAsset, str]:
    """Upload one run-unique native artifact, then create its database row."""
    upload = upload or upload_file_to_storage
    create_asset = create_asset or create_model_asset
    safe_filename = normalize_storage_filename(
        slicer_result.artifact_filename,
        fallback_stem=_preferred_gcode_filename(product, slicer_result.engine_key),
    )
    key = gcode_storage_key(product.id, safe_filename, run_id=run.id)
    publication.storage_reference = planned_storage_reference(
        bucket=bucket,
        key=key,
        local_root=local_root,
    )
    publication.artifact_size = slicer_result.artifact_size
    publication.artifact_sha256 = slicer_result.artifact_sha256
    storage_reference = upload(
        slicer_result.artifact_path,
        bucket=bucket,
        key=key,
        local_root=local_root,
        content_type=slicer_result.artifact_media_type,
    )
    # Track immediately: create_model_asset flushes, so any following exception
    # must compensate this exact run-unique object after rolling back.
    publication.storage_reference = storage_reference
    asset = create_asset(
        product,
        storage_reference=storage_reference,
        original_filename=slicer_result.artifact_filename,
        safe_filename=safe_filename,
        content_type=slicer_result.artifact_media_type,
        size_bytes=slicer_result.artifact_size,
        sha256=slicer_result.artifact_sha256,
        asset_kind=AssetKind.GCODE,
    )
    return asset, storage_reference


def _dispatch_completion_side_effects(
    *,
    product: Product,
    slicer_result,
    convert_dispatch=None,
    audit_record=None,
) -> str | None:
    """Dispatch best-effort work after the analysis commit without reopening it."""
    convert_dispatch = convert_dispatch or convert_product_model_for_viewer.delay
    audit_record = audit_record or get_audit_client().record
    convert_task_id = None
    if product.model_convert_to_glb:
        try:
            convert_task = convert_dispatch(product.id)
            convert_task_id = getattr(convert_task, "id", None)
        except Exception:
            logger.exception(
                "committed model analysis GLB dispatch failed for product %s",
                product.id,
            )
    try:
        audit_record(
            action="model_analysis.completed",
            entity_type="product",
            entity_id=str(product.id),
            actor_type="system",
            source_module="app.tasks.model_analysis",
            tenant_id=str(product.business_id) if product.business_id else None,
            metadata={
                "percent": 100,
                "conversion_queued": convert_task_id is not None,
                "outcome": "success",
                "engine_key": slicer_result.engine_key,
                "fallback_used": slicer_result.fallback_used,
                "estimate_only": slicer_result.estimate_only,
                "artifact_sha256": slicer_result.artifact_sha256,
            },
        )
    except Exception:
        logger.exception(
            "committed model analysis completion audit failed for product %s",
            product.id,
        )
    return convert_task_id


def _apply_initial_cost_snapshot(
    product: Product,
    *,
    run_id: int | None = None,
    model_asset_id: int | None = None,
    material: str | None = None,
    density: Decimal | None = None,
    density_source: str | None = None,
    scale_percent: int | None = None,
    copies: int | None = None,
    cost_resolver_evidence: dict | None = None,
) -> None:
    breakdown = calculate_product_cost(product=product)
    product.estimated_material_cost = breakdown.material_cost
    product.estimated_profit = breakdown.margin_dollars
    product.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
    persist_cost_snapshot(
        product=product,
        breakdown=breakdown,
        snapshot_reason="model_analysis.product",
        analysis_run_id=run_id,
        model_asset_id=model_asset_id,
        material=material,
        density=density,
        density_source=density_source,
        scale_percent=normalize_scale_percent(scale_percent),
        copies=copies,
        cost_resolver_evidence=cost_resolver_evidence,
    )


def _record_analysis_step(task, product: Product, *, step: str, percent: int, message: str) -> None:
    task.update_state(
        state="PROGRESS",
        meta={"step": step, "percent": percent, "message": message},
    )
    config = product.model_analysis_config or {}
    action = {
        "started": "model_analysis.started",
        "downloaded": "model_analysis.file_downloaded",
        "validated": "model_analysis.validated",
        "slicing": "model_analysis.slicing_started",
        "sliced": "model_analysis.sliced",
        "gcode_stored": "model_analysis.gcode_stored",
        "costed": "model_analysis.costed",
        "conversion_started": "model_analysis.conversion_started",
    }.get(step, f"model_analysis.{step}")
    get_audit_client().record(
        action=action,
        entity_type="product",
        entity_id=str(product.id),
        actor_id=config.get("uploaded_by") if config.get("uploaded_by") else None,
        actor_type="user" if config.get("uploaded_by") else "system",
        source_module="app.tasks.model_analysis",
        tenant_id=str(product.business_id) if product.business_id else None,
        metadata={"percent": percent, "message": message},
    )


def _resolve_material_cost(
    product: Product, material: str | None, spool_id: int | None
) -> tuple[Decimal, int | None, dict]:
    """Resolve a cost-per-gram, falling back to the legacy weighted average."""
    try:
        from app.services.cost_engine import resolve_material_cost

        resolver = resolve_material_cost(
            product.business_id,
            material,
            spool_id=spool_id,
        )
        return resolver.cost_per_gram, resolver.spool_id, resolver.evidence
    except ImportError:
        from app.services.cost_engine import _best_spool_match

        cost_per_gram, spool_id = _best_spool_match()
        return cost_per_gram, spool_id, {}


@celery.task(bind=True, max_retries=2, default_retry_delay=30)
def analyze_product_model(self, product_id: int, run_id: int) -> dict:
    """Analyze one product model and publish results through a race-proof run.

    The route passes the exact ``ProductAnalysisRun`` identity. Only its queued
    current run can be claimed; stale or duplicate deliveries exit before any
    analysis side effect.
    """
    work_dir: Path | None = None
    gcode_path: Path | None = None
    publication = _ArtifactPublicationState()
    run = None

    try:
        run = claim_analysis_run(product_id, run_id)
        if run is None:
            return task_envelope(
                False,
                data={"product_id": product_id, "run_id": run_id, "idempotent": True},
                error="analysis run is not claimable",
            )

        product = db.session.get(Product, product_id)
        if product is None:  # Defensive; the run FK should make this impossible.
            raise RuntimeError("Product not found for claimed analysis run")

        _record_analysis_step(
            self, product, step="started", percent=5, message="Preparing model analysis"
        )

        file_location = run.source_asset.storage_reference if run.source_asset else None
        if not file_location:
            raise ValueError("No source asset set on analysis run")

        # mkdtemp creates the exclusive 0700 workspace required by SlicerClient.
        # This task retains it unchanged for the complete analysis attempt and
        # removes it only in the task's finally block.
        tmp_dir = Path(tempfile.mkdtemp(prefix="dfp-model-"))
        tmp_dir.chmod(0o700)
        work_dir = tmp_dir

        if is_s3_reference(file_location):
            data = download_storage_bytes(file_location)
            ext = Path(storage_reference_name(file_location)).suffix or ".stl"
            model_path = tmp_dir / f"model{ext}"
            model_path.write_bytes(data)
        else:
            model_path = Path(file_location)

        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        _record_analysis_step(
            self, product, step="downloaded", percent=15, message="Model file ready"
        )

        analysis_config = dict(run.settings_json or {})
        embedded_settings = extract_3mf_slicer_settings(model_path)

        # Issue 9/30 — apply scale_percent BEFORE slicing/validation so the
        # stored bounding box and slicer estimates reflect the scaled size.
        # The studio stores a stringified Decimal ("100.00"); normalize to int
        # here so products already written with that shape still work.
        scale_percent = normalize_scale_percent(analysis_config.get("scale_percent"))
        analysis_path = model_path
        if scale_percent is not None and scale_percent != 100:
            try:
                scaled_mesh = apply_scale(model_path, scale_percent)
                if scaled_mesh is not None:
                    scaled_path = tmp_dir / "scaled.stl"
                    scaled_mesh.export(str(scaled_path))
                    analysis_path = scaled_path
            except Exception as exc:  # pragma: no cover - defensive
                import logging

                logging.getLogger(__name__).warning(
                    "Scale apply failed for product %s: %s", product.id, exc
                )

        set_run_status(run, AnalysisRunStatus.VALIDATING)
        db.session.commit()

        validation = validate_model_file(analysis_path)
        if not validation.success:
            if publish_run_results(run, product, error=validation.error):
                db.session.commit()
            get_audit_client().record(
                action="model_analysis.failed",
                entity_type="product",
                entity_id=str(product.id),
                actor_type="system",
                source_module="app.tasks.model_analysis",
                metadata={"step": "validation", "error": validation.error, "outcome": "failure"},
            )
            return task_envelope(False, error=validation.error)

        # Apply embedded 3MF settings when requested (scalar config only).
        if analysis_config.get("use_embedded_settings") and embedded_settings:
            mapping = {
                "fill_density": "infill_percent",
                "fill_pattern": "infill_pattern",
                "filament_type": "material",
            }
            for source_key, raw_value in embedded_settings.items():
                target_key = mapping.get(source_key, source_key)
                value = raw_value[0] if isinstance(raw_value, list) and raw_value else raw_value
                if target_key == "support_material":
                    target_key = "supports"
                    value = "everywhere" if str(value).lower() in {"1", "true"} else "none"
                analysis_config[target_key] = value
            build_plate_only = str(
                embedded_settings.get("support_material_buildplate_only", "0")
            ).lower()
            if build_plate_only in {"1", "true"}:
                analysis_config["supports"] = "build_plate"
            analysis_config["embedded_settings_applied"] = True

        geometry = {
            **validation.bounding_box,
            "is_watertight": validation.is_watertight,
            "printer_fit": validation.printer_fit,
            "scale_warning": validation.scale_warning,
            "format_detected": validation.format_detected,
        }
        # Keep effective scalar settings on the exact run. The Product summary
        # is updated only during the row-locked final publication.
        run.settings_json = sanitize_analysis_config(analysis_config)
        run.embedded_settings_json = embedded_settings
        db.session.commit()
        _record_analysis_step(
            self, product, step="validated", percent=35, message="Geometry validation complete"
        )

        locked_after_validation = lock_current_analysis_run_for_publish(product_id, run_id)
        if locked_after_validation is None:
            db.session.rollback()
            return task_envelope(False, error="superseded by a newer upload")
        product, run = locked_after_validation

        # Preview-only formats are not sliced (Issue 8): the upload route skips
        # slicing for these; if we somehow get here, publish geometry only.
        if not is_quotable_format(analysis_path):
            published = publish_run_results(
                run,
                product,
                geometry=geometry,
                slicer_stats={"slicer_skipped": True, "reason": "preview_only_format"},
                parsed_volume_mm3=Decimal(str(validation.volume_mm3)),
                parsed_surface_area_mm2=Decimal(str(validation.surface_area_mm2)),
                parsed_triangle_count=validation.triangle_count,
                already_locked=True,
            )
            db.session.commit()
            if not published:
                return task_envelope(False, error="superseded by a newer upload")
            _apply_initial_cost_snapshot(
                product,
                run_id=run.id,
                material=analysis_config.get("material"),
                scale_percent=scale_percent,
                copies=int(analysis_config.get("copies") or 1),
            )
            write_model_metadata(product)
            db.session.commit()
            return task_envelope(
                True,
                data={
                    "product_id": product.id,
                    "slicer_skipped": True,
                    "convert_task_id": None,
                },
            )

        set_run_status(run, AnalysisRunStatus.SLICING)
        product.analysis_status = "slicing"
        db.session.commit()
        _record_analysis_step(
            self, product, step="slicing", percent=45, message="Generating slicer estimates"
        )

        # Issue 9/30 — copies: slice ONE copy; per-unit cost = plate_cost / copies.
        copies = max(1, int(analysis_config.get("copies") or 1))

        slicer_result = slice_with_slicer(
            analysis_path,
            workspace=tmp_dir,
            profile_name=analysis_config.get("printer_profile"),
            slicer_options=analysis_config,
            preserve_orientation=analysis_config.get("preserve_orientation"),
        )

        if not slicer_result.success:
            slicer_errors = [str(slicer_result.error or "Slicer service returned no result")]
            error_msg = "Could not slice this model.\n" + slicer_errors[0]
            if publish_run_results(run, product, geometry=geometry, error=error_msg):
                db.session.commit()
            get_audit_client().record(
                action="model_analysis.failed",
                entity_type="product",
                entity_id=str(product.id),
                actor_type="system",
                source_module="app.tasks.model_analysis",
                metadata={"step": "slicing", "errors": slicer_errors, "outcome": "failure"},
            )
            return task_envelope(
                False,
                data={
                    "product_id": product.id,
                    "slicer_skipped": True,
                    "slicer_errors": slicer_errors,
                },
                error=error_msg,
            )

        unit_grams = slicer_result.filament_grams
        unit_minutes = slicer_result.print_minutes
        plate_grams = unit_grams * Decimal(copies)
        plate_minutes = unit_minutes * Decimal(copies)

        material = analysis_config.get("material")
        manual_density = analysis_config.get("filament_density")
        embedded_density = embedded_settings.get("filament_density") if embedded_settings else None
        density, density_source = resolve_density(
            material, embedded=embedded_density, manual=manual_density
        )
        cost_per_gram, spool_id, cost_evidence = _resolve_material_cost(
            product, material, analysis_config.get("spool_id")
        )
        plate_cost = (plate_grams * cost_per_gram).quantize(Decimal("0.01"))
        per_unit_cost = (plate_cost / Decimal(copies)).quantize(Decimal("0.01"))

        _record_analysis_step(
            self, product, step="sliced", percent=70, message="Slicer estimates complete"
        )
        gcode_path = slicer_result.artifact_path
        if gcode_path is None or not gcode_path.is_file():
            raise ValueError("Slicer service did not return a readable artifact")

        set_run_status(run, AnalysisRunStatus.STORING_GCODE)
        db.session.commit()

        # Lock and refresh the current run before creating a current generated
        # asset. The lock is held through publish + commit so a newer upload
        # cannot interleave and leave this superseded run's G-code current.
        locked_publication = lock_current_analysis_run_for_publish(product_id, run_id)
        if locked_publication is None:
            db.session.rollback()
            return task_envelope(False, error="superseded by a newer upload")
        product, run = locked_publication

        gcode_asset = None
        product.model_analysis_config = sanitize_analysis_config(analysis_config)
        if analysis_config.get("retain_gcode", True):
            gcode_asset, gcode_ref = _persist_slicer_artifact(
                product,
                run,
                slicer_result,
                publication,
                bucket=current_app.config.get("PRODUCT_ASSETS_BUCKET", "products"),
                local_root=current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products"),
            )
            product.gcode_path = gcode_ref
            _record_analysis_step(
                self, product, step="gcode_stored", percent=80, message="G-code stored"
            )

        slicer_stats = {
            "success": True,
            "engine_key": slicer_result.engine_key,
            "engine_name": slicer_result.engine_name,
            "engine_version": slicer_result.engine_version,
            "fallback_used": slicer_result.fallback_used,
            "primary_failure": slicer_result.stats.get("primary_failure"),
            "filament_grams": str(unit_grams),
            "print_minutes": str(unit_minutes),
            "layer_count": slicer_result.stats.get("layer_count"),
            "profile_ids": slicer_result.stats.get("profile_ids", {}),
            "artifact_filename": slicer_result.artifact_filename,
            "artifact_media_type": slicer_result.artifact_media_type,
            "artifact_size": slicer_result.artifact_size,
            "artifact_sha256": slicer_result.artifact_sha256,
            "direct_print_eligible": slicer_result.direct_print_eligible,
            "estimate_only": slicer_result.estimate_only,
            "profile_used": slicer_result.profile_used,
            "copies": copies,
            "plate_grams": str(plate_grams),
            "plate_minutes": str(plate_minutes),
            "plate_cost": str(plate_cost),
            "per_unit_cost": str(per_unit_cost),
            "cost_per_gram": str(cost_per_gram),
            "spool_id": spool_id,
            "density": str(density),
            "density_source": density_source,
            "scale_percent": scale_percent,
            "material_default_temp": material_default_temp(material),
        }
        # (c) publish results to the run + product summary fields. publish_run_results
        # sets run.status=COMPLETE, so the COSTING progress flag is set just before.
        set_run_status(run, AnalysisRunStatus.COSTING)
        published = publish_run_results(
            run,
            product,
            geometry=geometry,
            slicer_stats=slicer_stats,
            parsed_volume_mm3=Decimal(str(validation.volume_mm3)),
            parsed_surface_area_mm2=Decimal(str(validation.surface_area_mm2)),
            parsed_triangle_count=validation.triangle_count,
            parsed_filament_grams=unit_grams,
            parsed_print_minutes=unit_minutes,
            parsed_material_cost=per_unit_cost,
            gcode_asset_id=gcode_asset.id if gcode_asset is not None else None,
            already_locked=True,
        )
        if not published:
            db.session.commit()
            return task_envelope(False, error="superseded by a newer upload")

        _apply_initial_cost_snapshot(
            product,
            run_id=run.id,
            material=material,
            density=density,
            density_source=density_source,
            scale_percent=scale_percent,
            copies=copies,
            cost_resolver_evidence=cost_evidence or None,
        )
        _record_analysis_step(
            self, product, step="costed", percent=90, message="Cost estimate complete"
        )
        write_model_metadata(product)
        publication.commit_attempted = True
        db.session.commit()
        publication.committed = True

        convert_task_id = _dispatch_completion_side_effects(
            product=product,
            slicer_result=slicer_result,
        )
        return task_envelope(
            True,
            data={
                "product_id": product.id,
                "filament_grams": str(unit_grams),
                "print_minutes": str(unit_minutes),
                "plate_grams": str(plate_grams),
                "plate_cost": str(plate_cost),
                "per_unit_cost": str(per_unit_cost),
                "copies": copies,
                "slicer_profile": slicer_result.profile_used,
                "convert_task_id": convert_task_id,
            },
        )
    except Exception as exc:
        logger.exception("model analysis failed for run %s", run_id)
        retry_count = int(getattr(self.request, "retries", 0) or 0)
        retries_remain = retry_count < int(self.max_retries or 0)
        _recover_failed_publication(
            publication,
            product_id=product_id,
            run_id=run_id,
            original_error=exc,
            mark_failed=(lambda **kwargs: None) if retries_remain else None,
        )
        try:
            get_audit_client().record(
                action="model_analysis.failed",
                entity_type="product",
                entity_id=str(product_id),
                actor_type="system",
                source_module="app.tasks.model_analysis",
                metadata={"run_id": run_id, "error": str(exc), "outcome": "failure"},
            )
        except Exception:
            logger.exception("model analysis failure audit dispatch failed")
        if retries_remain and requeue_analysis_run(product_id, run_id):
            raise analyze_product_model.retry(exc=exc)
        if retries_remain:
            try:
                _mark_run_failed_fresh(product_id=product_id, run_id=run_id, error=str(exc))
            except Exception:
                logger.exception("analysis retry could not requeue or mark run failed")
        raise
    finally:
        if work_dir and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        if gcode_path and gcode_path.exists():
            try:
                gcode_path.unlink()
            except Exception:
                pass


@celery.task(bind=True, max_retries=1)
def convert_product_model_for_viewer(self, product_id: int) -> dict:
    product = db.session.get(Product, product_id)
    if product is None:
        return task_envelope(False, error="Product not found")

    try:
        _record_analysis_step(
            self, product, step="conversion_started", percent=10, message="Creating GLB preview"
        )
        file_location = product.model_file_path
        if not file_location:
            return task_envelope(False, error="No file location")

        ext = Path(file_location).suffix.lower()
        if ext == ".glb":
            product.convert_status = "complete"
            product.converted_model_path = file_location
            db.session.commit()
            return task_envelope(True, data={"converted_path": file_location})

        tmp_dir = Path(tempfile.mkdtemp(prefix="dfp-convert-"))
        data = download_storage_bytes(file_location)
        source_path = tmp_dir / f"source{ext}"
        source_path.write_bytes(data)

        output_path = tmp_dir / "converted.glb"
        converted = convert_to_glb(source_path, output_path)
        if converted is None:
            product.convert_status = "failed"
            product.conversion_error = "Conversion to GLB failed"
            db.session.commit()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return task_envelope(False, error="Conversion failed")

        bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
        local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
        key = converted_storage_key(product.id, _preferred_converted_filename(product))
        storage_ref = upload_file_to_storage(
            output_path,
            bucket=bucket,
            key=key,
            local_root=local_root,
            content_type="model/gltf-binary",
        )

        shutil.rmtree(tmp_dir, ignore_errors=True)
        product.convert_status = "complete"
        product.converted_model_path = storage_ref
        write_model_metadata(product)
        db.session.commit()
        get_audit_client().record(
            action="model_analysis.conversion_completed",
            entity_type="product",
            entity_id=str(product.id),
            actor_type="system",
            source_module="app.tasks.model_analysis",
            tenant_id=str(product.business_id) if product.business_id else None,
            metadata={"converted_model_path": storage_ref, "outcome": "success"},
        )
        return task_envelope(True, data={"converted_path": storage_ref})
    except Exception as exc:
        product.convert_status = "failed"
        product.conversion_error = str(exc)
        db.session.commit()
        return task_envelope(False, error=str(exc))
