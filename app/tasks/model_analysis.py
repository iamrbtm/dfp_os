from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from flask import current_app

from app.celery_app import celery
from app.extensions import db
from app.models.catalog import Product
from app.services.cost_engine import calculate_product_cost, persist_cost_snapshot
from app.services.model_analysis import convert_to_glb, slice_with_prusaslicer, validate_model_file
from app.services.storage import (
    converted_storage_key,
    download_storage_bytes,
    gcode_storage_key,
    is_s3_reference,
    normalize_storage_filename,
    storage_reference_name,
    storage_slug,
    upload_bytes_to_storage,
    upload_file_to_storage,
)


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
    persist_cost_snapshot(product=product, breakdown=breakdown, snapshot_reason="model_analysis.product")


@celery.task(bind=True, max_retries=2, default_retry_delay=30)
def analyze_product_model(self, product_id: int) -> dict:
    product = db.session.get(Product, product_id)
    if product is None:
        return {"success": False, "error": "Product not found"}

    work_dir: Path | None = None
    gcode_path: Path | None = None

    try:
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

        validation = validate_model_file(model_path)
        if not validation.success:
            product.analysis_status = "failed"
            product.analysis_error = validation.error
            db.session.commit()
            return {"success": False, "error": validation.error}

        product.parsed_volume_mm3 = Decimal(str(validation.volume_mm3))
        product.parsed_surface_area_mm2 = Decimal(str(validation.surface_area_mm2))
        product.parsed_triangle_count = validation.triangle_count
        db.session.commit()

        product.analysis_status = "slicing"
        db.session.commit()

        gcode_out = tmp_dir / "quote.gcode"
        slicer_errors: list[str] = []
        slicer_result = slice_with_prusaslicer(model_path, profile_name=None, output_path=gcode_out)

        if not slicer_result.success:
            slicer_errors.append(f"centered: {slicer_result.error}")
            slicer_result = slice_with_prusaslicer(
                model_path,
                profile_name=None,
                output_path=gcode_out,
                center=None,
            )

        if not slicer_result.success:
            slicer_errors.append(f"uncentered: {slicer_result.error}")
            product.analysis_status = "failed"
            product.analysis_error = "Could not slice this model with PrusaSlicer.\n" + "\n".join(slicer_errors)
            product.analysis_completed_at = datetime.now(timezone.utc)
            db.session.commit()
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
        gcode_path = gcode_out

        if gcode_path and gcode_path.exists():
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
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning(
                    "Failed to upload G-code for product %s: %s", product.id, exc
                )

        product.analysis_status = "complete"
        product.analysis_completed_at = datetime.now(timezone.utc)
        _apply_initial_cost_snapshot(product)
        db.session.commit()

        convert_task = convert_product_model_for_viewer.delay(product_id)
        return {
            "success": True,
            "product_id": product.id,
            "filament_grams": str(slicer_result.filament_grams),
            "print_minutes": str(slicer_result.print_minutes),
            "slicer_profile": slicer_result.profile_used,
            "convert_task_id": convert_task.id,
        }
    except Exception as exc:
        product.analysis_status = "failed"
        product.analysis_error = str(exc)
        db.session.commit()
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
        db.session.commit()
        return {"success": True, "converted_path": storage_ref}
    except Exception as exc:
        product.convert_status = "failed"
        product.conversion_error = str(exc)
        db.session.commit()
        return {"success": False, "error": str(exc)}
