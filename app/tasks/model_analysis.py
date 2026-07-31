from __future__ import annotations

import shutil
import tempfile
import hashlib
import json
import uuid
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
    slice_with_prusaslicer,
    task_envelope,
    validate_model_file,
)
from app.services.product_analysis import (
    create_model_asset,
    get_current_run,
    is_current_run,
    publish_run_results,
    sanitize_analysis_config,
    set_run_status,
    start_analysis_run,
)
from app.services.materials import material_default_temp, resolve_density
from app.services.storage import (
    converted_storage_key,
    download_storage_bytes,
    gcode_storage_key,
    is_s3_reference,
    normalize_storage_filename,
    product_storage_key,
    storage_reference_name,
    storage_slug,
    upload_bytes_to_storage,
    upload_file_to_storage,
)


def _record_pmp_step(task, product: Product, actor_id: int | None, *, step: str, percent: int, message: str) -> None:
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
        _record_pmp_step(self, product, actor_id, step="started", percent=5, message="PMP packing started")
        source_bytes = download_storage_bytes(source_reference)
        _record_pmp_step(self, product, actor_id, step="downloaded", percent=20, message="Source model downloaded")

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
        _record_pmp_step(self, product, actor_id, step="packed", percent=75, message=f"PMP placed {result['placed']} copies")

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
            "source": {"filename": source_name, "reference": source_reference, "size_bytes": len(source_bytes), "sha256": hashlib.sha256(source_bytes).hexdigest(), "format": result["source_format"]},
            "pmp": {
                "bed_width_mm": bed_w, "bed_depth_mm": bed_d, "spacing_mm": 2.0,
                "margin_mm": 3.5, "angle_step_degrees": 15.0, "mode": "auto",
                "tower": "auto", "printer_profile": profile_stem, "scale": result["scale"],
                "placed": result["placed"], "method": result["method"],
                "bed_utilization": result["utilization"],
                "usable_utilization": result["usable_utilization"],
                "warnings": result["warnings"], "reserved_area": result["reserve"],
            },
            "output": {"filename": output_name, "reference": output_ref, "size_bytes": len(output_bytes), "sha256": hashlib.sha256(output_bytes).hexdigest()},
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
        _record_pmp_step(self, product, actor_id, step="stored", percent=95, message="Packed plate and metadata saved")
        get_audit_client().record(
            action="product_model.pmp.completed", entity_type="product", entity_id=str(product.id),
            actor_id=str(actor_id) if actor_id else None, actor_type="user" if actor_id else "system",
            source_module="app.tasks.model_analysis", tenant_id=str(product.business_id) if product.business_id else None,
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
            action="product_model.pmp.failed", entity_type="product", entity_id=str(product.id),
            actor_id=str(actor_id) if actor_id else None, actor_type="user" if actor_id else "system",
            source_module="app.tasks.model_analysis", tenant_id=str(product.business_id) if product.business_id else None,
            metadata={"error": str(exc)},
        )
        raise
    finally:
        if out_path is not None:
            shutil.rmtree(out_path.parent, ignore_errors=True)


def _preferred_gcode_filename(product: Product) -> str:
    label = product.slug or product.name or f"product-{product.id or 0}"
    return f"{storage_slug(label, fallback=f'product-{product.id or 0}')}.gcode"


def _preferred_converted_filename(product: Product) -> str:
    source_name = storage_reference_name(product.model_file_path)
    source_stem = Path(source_name).stem if source_name else f"product-{product.id or 0}"
    return normalize_storage_filename(f"{source_stem}.glb")


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
        scale_percent=scale_percent,
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


def _ensure_run_for_product(product: Product) -> tuple[Product, "object"]:
    """Defensive fallback: if no current run exists, build a source asset and run.

    The upload route normally creates the run before enqueueing. If it did not
    (older caller, manual test), synthesize one from ``product.model_file_path``
    so the race-proof machinery still has a run to publish through.
    """
    file_location = product.model_file_path
    if not file_location:
        raise ValueError("No file location set on product")
    source_name = storage_reference_name(file_location) or Path(file_location).name or "model"
    try:
        if is_s3_reference(file_location):
            data = download_storage_bytes(file_location)
        else:
            data = Path(file_location).read_bytes()
    except Exception:
        data = b""
    sha = hashlib.sha256(data).hexdigest() if data else "0" * 64
    asset = create_model_asset(
        product,
        storage_reference=file_location,
        original_filename=source_name,
        safe_filename=normalize_storage_filename(source_name),
        content_type="model/stl",
        size_bytes=len(data),
        sha256=sha,
        asset_kind=AssetKind.SOURCE_MODEL,
    )
    run = start_analysis_run(
        product,
        source_asset=asset,
        settings=sanitize_analysis_config(product.model_analysis_config),
    )
    db.session.flush()
    return product, run


def _resolve_material_cost(product: Product, material: str | None, spool_id: int | None) -> tuple[Decimal, int | None, dict]:
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
def analyze_product_model(self, product_id: int) -> dict:
    """Analyze one product model and publish results through a race-proof run.

    The route creates a ``ProductAnalysisRun`` before enqueueing. This task only
    writes to the ``Product`` summary fields while its run remains current
    (Issue 6). If a newer upload superseded this run, the task marks itself
    superseded and leaves the product alone.
    """
    product = db.session.get(Product, product_id)
    if product is None:
        return task_envelope(False, error="Product not found")

    work_dir: Path | None = None
    gcode_path: Path | None = None
    run = None

    try:
        _record_analysis_step(
            self, product, step="started", percent=5, message="Preparing model analysis"
        )

        # (a) locate the current run, or create one defensively.
        run = get_current_run(product)
        if run is None:
            product, run = _ensure_run_for_product(product)
            db.session.commit()

        # (b) race guard: if a newer upload superseded this run, bail out.
        if not is_current_run(run.id):
            set_run_status(run, AnalysisRunStatus.SUPERSEDED)
            db.session.commit()
            return task_envelope(False, error="superseded by a newer upload")

        set_run_status(run, AnalysisRunStatus.STARTED)
        product.analysis_status = "analyzing"
        db.session.commit()

        file_location = product.model_file_path
        if not file_location:
            raise ValueError("No file location set on product")

        tmp_dir = Path(tempfile.mkdtemp(prefix="dfp-model-"))
        work_dir = tmp_dir

        if is_s3_reference(file_location):
            data = download_storage_bytes(file_location)
            ext = Path(file_location).suffix or ".stl"
            model_path = tmp_dir / f"model{ext}"
            model_path.write_bytes(data)
        else:
            model_path = Path(file_location)

        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        _record_analysis_step(
            self, product, step="downloaded", percent=15, message="Model file ready"
        )

        analysis_config = dict(product.model_analysis_config or {})
        embedded_settings = extract_3mf_slicer_settings(model_path)

        # Issue 9/30 — apply scale_percent BEFORE slicing/validation so the
        # stored bounding box and slicer estimates reflect the scaled size.
        scale_percent = analysis_config.get("scale_percent")
        analysis_path = model_path
        if scale_percent is not None and str(scale_percent) not in {"", "100", "100.0"}:
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
            if is_current_run(run.id):
                publish_run_results(run, product, error=validation.error)
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
        # (d) only scalar settings may live on the Product row (Issue 40).
        product.model_analysis_config = sanitize_analysis_config(analysis_config)
        run.embedded_settings_json = embedded_settings
        db.session.commit()
        _record_analysis_step(
            self, product, step="validated", percent=35, message="Geometry validation complete"
        )

        if not is_current_run(run.id):
            set_run_status(run, AnalysisRunStatus.SUPERSEDED)
            db.session.commit()
            return task_envelope(False, error="superseded by a newer upload")

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
            )
            db.session.commit()
            if not published:
                return task_envelope(False, error="superseded by a newer upload")
            _apply_initial_cost_snapshot(
                product,
                run_id=run.id,
                material=analysis_config.get("material"),
                scale_percent=int(scale_percent) if scale_percent is not None else None,
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

        gcode_out = tmp_dir / "quote.gcode"
        slicer_errors: list[str] = []
        slicer_result = slice_with_prusaslicer(
            analysis_path,
            profile_name=analysis_config.get("printer_profile"),
            output_path=gcode_out,
            slicer_options=analysis_config,
            preserve_orientation=analysis_config.get("preserve_orientation"),
        )

        if not slicer_result.success:
            slicer_errors.append(f"centered: {slicer_result.error}")
            slicer_result = slice_with_prusaslicer(
                analysis_path,
                profile_name=None,
                output_path=gcode_out,
                center=None,
                slicer_options=analysis_config,
            )

        if not slicer_result.success:
            slicer_errors.append(f"uncentered: {slicer_result.error}")
            error_msg = "Could not slice this model with PrusaSlicer.\n" + "\n".join(
                slicer_errors
            )
            if is_current_run(run.id):
                publish_run_results(run, product, geometry=geometry, error=error_msg)
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

        # Race guard before publishing.
        if not is_current_run(run.id):
            set_run_status(run, AnalysisRunStatus.SUPERSEDED)
            db.session.commit()
            return task_envelope(False, error="superseded by a newer upload")

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
        gcode_path = gcode_out

        set_run_status(run, AnalysisRunStatus.STORING_GCODE)
        db.session.commit()

        if gcode_path and gcode_path.exists() and analysis_config.get("retain_gcode", True):
            try:
                gcode_key = gcode_storage_key(product.id, _preferred_gcode_filename(product))
                gcode_ref = upload_bytes_to_storage(
                    gcode_path.read_bytes(),
                    bucket=current_app.config.get("PRODUCT_ASSETS_BUCKET", "products"),
                    key=gcode_key,
                    local_root=current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products"),
                    content_type="text/plain",
                )
                product.gcode_path = gcode_ref
                _record_analysis_step(
                    self, product, step="gcode_stored", percent=80, message="G-code stored"
                )
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning(
                    "Failed to upload G-code for product %s: %s", product.id, exc
                )

        slicer_stats = {
            "filament_grams": str(unit_grams),
            "print_minutes": str(unit_minutes),
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
        for key, value in slicer_result.stats.items():
            slicer_stats[key] = str(value) if isinstance(value, Decimal) else value

        # (c) publish results to the run + product summary fields. publish_run_results
        # sets run.status=COMPLETE, so the COSTING progress flag is set just before.
        set_run_status(run, AnalysisRunStatus.COSTING)
        db.session.commit()
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
            scale_percent=int(scale_percent) if scale_percent is not None else None,
            copies=copies,
            cost_resolver_evidence=cost_evidence or None,
        )
        _record_analysis_step(
            self, product, step="costed", percent=90, message="Cost estimate complete"
        )
        write_model_metadata(product)
        db.session.commit()

        convert_task = (
            convert_product_model_for_viewer.delay(product_id)
            if product.model_convert_to_glb
            else None
        )
        get_audit_client().record(
            action="model_analysis.completed",
            entity_type="product",
            entity_id=str(product.id),
            actor_type="system",
            source_module="app.tasks.model_analysis",
            tenant_id=str(product.business_id) if product.business_id else None,
            metadata={
                "percent": 100,
                "conversion_queued": bool(convert_task),
                "outcome": "success",
            },
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
                "convert_task_id": convert_task.id if convert_task else None,
            },
        )
    except Exception as exc:
        # (e) on failure, publish the error only if this run is still current.
        if run is not None and is_current_run(run.id):
            publish_run_results(run, product, error=str(exc))
            db.session.commit()
        else:
            product.analysis_status = "failed"
            product.analysis_error = str(exc)
            db.session.commit()
        get_audit_client().record(
            action="model_analysis.failed",
            entity_type="product",
            entity_id=str(product.id),
            actor_type="system",
            source_module="app.tasks.model_analysis",
            metadata={"error": str(exc), "outcome": "failure"},
        )
        raise analyze_product_model.retry(exc=exc)
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
