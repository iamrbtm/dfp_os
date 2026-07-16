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
from app.models.catalog import Product
from app.services.cost_engine import calculate_product_cost, persist_cost_snapshot
from app.services.audit_client import get_audit_client
from app.services.model_asset_metadata import write_model_metadata
from app.services.model_analysis import (
    convert_to_glb,
    extract_3mf_slicer_settings,
    slice_with_prusaslicer,
    validate_model_file,
)
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
def pack_product_model(self, product_id: int, source_reference: str, source_name: str, actor_id: int | None = None) -> dict:
    """Run PMP for one verified product asset and store its generated artifacts."""
    product = db.session.get(Product, product_id)
    if product is None:
        return {"success": False, "error": "Product not found"}
    out_path: Path | None = None
    try:
        _record_pmp_step(self, product, actor_id, step="started", percent=5, message="PMP packing started")
        source_bytes = download_storage_bytes(source_reference)
        _record_pmp_step(self, product, actor_id, step="downloaded", percent=20, message="Source model downloaded")

        from pmp import pack_model_bytes

        result = pack_model_bytes(
            source_bytes,
            source_name,
            target=None,
            spacing=2.0,
            bed_w=270.0,
            bed_d=270.0,
            count=None,
            angle_step=15.0,
            pack_mode="auto",
            tower="auto",
            margin=3.5,
            printer="u1",
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
                "bed_width_mm": 270.0, "bed_depth_mm": 270.0, "spacing_mm": 2.0,
                "margin_mm": 3.5, "angle_step_degrees": 15.0, "mode": "auto",
                "tower": "auto", "printer_profile": "u1", "scale": result["scale"],
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
        return {"success": True, "filename": output_name, "reference": output_ref, "metadata_reference": metadata_ref, "placed": result["placed"]}
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


def _apply_initial_cost_snapshot(product: Product) -> None:
    breakdown = calculate_product_cost(product=product)
    product.estimated_material_cost = breakdown.material_cost
    product.estimated_profit = breakdown.margin_dollars
    product.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
    persist_cost_snapshot(
        product=product, breakdown=breakdown, snapshot_reason="model_analysis.product"
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
        actor_id=str(config.get("uploaded_by")) if config.get("uploaded_by") else None,
        actor_type="user" if config.get("uploaded_by") else "system",
        source_module="app.tasks.model_analysis",
        tenant_id=str(product.business_id) if product.business_id else None,
        metadata={"percent": percent, "message": message},
    )


@celery.task(bind=True, max_retries=2, default_retry_delay=30)
def analyze_product_model(self, product_id: int) -> dict:
    product = db.session.get(Product, product_id)
    if product is None:
        return {"success": False, "error": "Product not found"}

    work_dir: Path | None = None
    gcode_path: Path | None = None

    try:
        _record_analysis_step(
            self, product, step="started", percent=5, message="Preparing model analysis"
        )
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
        validation = validate_model_file(model_path)
        if not validation.success:
            product.analysis_status = "failed"
            product.analysis_error = validation.error
            db.session.commit()
            get_audit_client().record(
                action="model_analysis.failed",
                entity_type="product",
                entity_id=str(product.id),
                actor_type="system",
                source_module="app.tasks.model_analysis",
                metadata={"step": "validation", "error": validation.error},
            )
            return {"success": False, "error": validation.error}

        product.parsed_volume_mm3 = Decimal(str(validation.volume_mm3))
        product.parsed_surface_area_mm2 = Decimal(str(validation.surface_area_mm2))
        product.parsed_triangle_count = validation.triangle_count
        analysis_config = dict(product.model_analysis_config or {})
        embedded_settings = extract_3mf_slicer_settings(model_path)
        analysis_config["embedded_settings_detected"] = embedded_settings
        if analysis_config.get("use_embedded_settings") and embedded_settings:
            mapping = {
                "fill_density": "infill_percent",
                "fill_pattern": "infill_pattern",
                "filament_type": "material",
            }
            for source_key, raw_value in embedded_settings.items():
                target_key = mapping.get(source_key, source_key)
                value = raw_value[0] if isinstance(raw_value, list) and raw_value else raw_value
                if target_key == "infill_percent":
                    value = str(value).rstrip("%")
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
        analysis_config["geometry"] = {
            **validation.bounding_box,
            "is_watertight": validation.is_watertight,
            "printer_fit": validation.printer_fit,
            "scale_warning": validation.scale_warning,
            "format_detected": validation.format_detected,
        }
        product.model_analysis_config = analysis_config
        db.session.commit()
        _record_analysis_step(
            self, product, step="validated", percent=35, message="Geometry validation complete"
        )

        product.analysis_status = "slicing"
        db.session.commit()
        _record_analysis_step(
            self, product, step="slicing", percent=45, message="Generating slicer estimates"
        )

        gcode_out = tmp_dir / "quote.gcode"
        slicer_errors: list[str] = []
        slicer_result = slice_with_prusaslicer(
            model_path,
            profile_name=analysis_config.get("printer_profile"),
            output_path=gcode_out,
            slicer_options=analysis_config,
        )

        if not slicer_result.success:
            slicer_errors.append(f"centered: {slicer_result.error}")
            slicer_result = slice_with_prusaslicer(
                model_path,
                profile_name=None,
                output_path=gcode_out,
                center=None,
                slicer_options=analysis_config,
            )

        if not slicer_result.success:
            slicer_errors.append(f"uncentered: {slicer_result.error}")
            product.analysis_status = "failed"
            product.analysis_error = "Could not slice this model with PrusaSlicer.\n" + "\n".join(
                slicer_errors
            )
            product.analysis_completed_at = datetime.now(timezone.utc)
            db.session.commit()
            get_audit_client().record(
                action="model_analysis.failed",
                entity_type="product",
                entity_id=str(product.id),
                actor_type="system",
                source_module="app.tasks.model_analysis",
                metadata={"step": "slicing", "errors": slicer_errors},
            )
            return {
                "success": False,
                "product_id": product.id,
                "slicer_skipped": True,
                "slicer_errors": slicer_errors,
            }

        product.parsed_filament_grams = slicer_result.filament_grams
        product.parsed_print_minutes = slicer_result.print_minutes
        from app.services.cost_engine import _best_spool_match

        cost_per_gram, _spool_id = _best_spool_match()
        product.parsed_material_cost = (slicer_result.filament_grams * cost_per_gram).quantize(
            Decimal("0.01")
        )
        _record_analysis_step(
            self, product, step="sliced", percent=70, message="Slicer estimates complete"
        )
        gcode_path = gcode_out

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

        product.analysis_status = "complete"
        product.analysis_completed_at = datetime.now(timezone.utc)
        analysis_config["slicer_results"] = {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in slicer_result.stats.items()
        }
        product.model_analysis_config = analysis_config
        _apply_initial_cost_snapshot(product)
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
            metadata={"percent": 100, "conversion_queued": bool(convert_task)},
        )
        return {
            "success": True,
            "product_id": product.id,
            "filament_grams": str(slicer_result.filament_grams),
            "print_minutes": str(slicer_result.print_minutes),
            "slicer_profile": slicer_result.profile_used,
            "convert_task_id": convert_task.id if convert_task else None,
        }
    except Exception as exc:
        product.analysis_status = "failed"
        product.analysis_error = str(exc)
        db.session.commit()
        get_audit_client().record(
            action="model_analysis.failed",
            entity_type="product",
            entity_id=str(product.id),
            actor_type="system",
            source_module="app.tasks.model_analysis",
            metadata={"error": str(exc)},
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
        return {"success": False, "error": "Product not found"}

    try:
        _record_analysis_step(
            self, product, step="conversion_started", percent=10, message="Creating GLB preview"
        )
        file_location = product.model_file_path
        if not file_location:
            return {"success": False, "error": "No file location"}

        ext = Path(file_location).suffix.lower()
        if ext == ".glb":
            product.convert_status = "complete"
            product.converted_model_path = file_location
            db.session.commit()
            return {"success": True, "converted_path": file_location}

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
            return {"success": False, "error": "Conversion failed"}

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
            metadata={"converted_model_path": storage_ref},
        )
        return {"success": True, "converted_path": storage_ref}
    except Exception as exc:
        product.convert_status = "failed"
        product.conversion_error = str(exc)
        db.session.commit()
        return {"success": False, "error": str(exc)}
