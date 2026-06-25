from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from flask import current_app

from app.celery_app import celery
from app.extensions import db
from app.models.catalog import ModelAsset
from app.services.cost_engine import calculate_product_cost
from app.services.model_analysis import (
    convert_to_glb,
    slice_with_prusaslicer,
    validate_model_file,
)
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


def _preferred_gcode_filename(asset: ModelAsset) -> str:
    if asset.variant is not None:
        label = asset.variant.size or asset.variant.name or asset.variant.sku or f"variant-{asset.variant_id}"
        return f"{storage_slug(label, fallback=f'variant-{asset.variant_id or asset.id or 0}')}.gcode"

    if asset.product is not None:
        label = asset.product.slug or asset.product.name or f"product-{asset.related_product_id or asset.id or 0}"
        return f"{storage_slug(label, fallback=f'product-{asset.related_product_id or asset.id or 0}')}.gcode"

    source_name = storage_reference_name(asset.file_location)
    if source_name:
        return f"{Path(source_name).stem}.gcode"
    return f"asset-{asset.id or 0}.gcode"


def _preferred_converted_filename(asset: ModelAsset) -> str:
    source_name = storage_reference_name(asset.file_location)
    source_stem = Path(source_name).stem if source_name else f"asset-{asset.id or 0}"
    if asset.variant_id is not None:
        return normalize_storage_filename(f"{asset.variant_id}_{source_stem}.glb")
    return normalize_storage_filename(f"{source_stem}.glb")


def _load_cost_settings() -> dict[str, Decimal]:
    settings = {
        "cost_per_gram": Decimal("0.025"),
        "labor_rate": Decimal("18.00"),
        "packaging_cost": Decimal("0.50"),
        "machine_hour_rate": Decimal("0.50"),
        "failure_rate": Decimal("0.05"),
        "target_margin_percent": Decimal("55.00"),
    }
    try:
        from app.services.settings import get_setting
        settings["cost_per_gram"] = Decimal(str(get_setting("cost_engine_cost_per_gram", "0.025")))
        settings["labor_rate"] = Decimal(str(get_setting("cost_engine_labor_rate", "18.00")))
        settings["packaging_cost"] = Decimal(str(get_setting("cost_engine_packaging_cost", "0.50")))
        settings["machine_hour_rate"] = Decimal(str(get_setting("cost_engine_machine_hour_rate", "0.50")))
        settings["failure_rate"] = Decimal(str(get_setting("cost_engine_failure_rate", "0.05")))
        settings["target_margin_percent"] = Decimal(str(get_setting("cost_engine_target_margin_percent", "55.00")))
    except Exception:
        pass
    return settings


def _apply_initial_cost_snapshot(asset: ModelAsset) -> None:
    product = asset.product
    if product is None:
        return

    settings = _load_cost_settings()
    if asset.variant is not None:
        breakdown = calculate_product_cost(
            product=product,
            variant=asset.variant,
            sale_price=asset.variant.price,
            cost_per_gram=settings["cost_per_gram"],
            labor_rate=settings["labor_rate"],
            packaging_cost=settings["packaging_cost"],
            machine_hour_rate=settings["machine_hour_rate"],
            failure_rate=settings["failure_rate"],
            target_margin_percent=settings["target_margin_percent"],
        )
        asset.variant.material_cost = breakdown.material_cost
        asset.variant.estimated_filament_grams = int(round(float(breakdown.filament_grams)))
        asset.variant.estimated_print_minutes = int(round(float(breakdown.print_minutes)))
        return

    breakdown = calculate_product_cost(
        product=product,
        variant=None,
        cost_per_gram=settings["cost_per_gram"],
        labor_rate=settings["labor_rate"],
        packaging_cost=settings["packaging_cost"],
        machine_hour_rate=settings["machine_hour_rate"],
        failure_rate=settings["failure_rate"],
        target_margin_percent=settings["target_margin_percent"],
    )
    product.estimated_material_cost = breakdown.material_cost
    product.estimated_profit = breakdown.margin_dollars
    product.estimated_print_minutes = int(round(float(breakdown.print_minutes)))


@celery.task(bind=True, max_retries=2, default_retry_delay=30)
def analyze_model_asset(self, asset_id: int) -> dict:
    asset = db.session.get(ModelAsset, asset_id)
    if asset is None:
        return {"success": False, "error": "Asset not found"}

    work_dir: Path | None = None
    gcode_path: Path | None = None

    try:
        asset.analysis_status = "analyzing"
        db.session.commit()

        file_location = asset.file_location
        if not file_location:
            raise ValueError("No file location set on asset")

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
            asset.analysis_status = "failed"
            asset.analysis_error = validation.error
            db.session.commit()
            return {"success": False, "error": validation.error}

        asset.parsed_volume_mm3 = Decimal(str(validation.volume_mm3))
        asset.parsed_surface_area_mm2 = Decimal(str(validation.surface_area_mm2))
        asset.parsed_triangle_count = validation.triangle_count
        db.session.commit()

        asset.analysis_status = "slicing"
        db.session.commit()

        gcode_out = tmp_dir / "quote.gcode"
        slicer_errors: list[str] = []

        slicer_result = slice_with_prusaslicer(
            model_path,
            profile_name=None,
            output_path=gcode_out,
        )

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
            asset.analysis_status = "failed"
            asset.analysis_error = (
                "Could not slice this model with PrusaSlicer.\n"
                + "\n".join(slicer_errors)
            )
            asset.analysis_completed_at = datetime.now(timezone.utc)
            db.session.commit()
            return {
                "success": False,
                "asset_id": asset.id,
                "slicer_skipped": True,
                "slicer_errors": slicer_errors,
                "validation": {
                    "volume_mm3": validation.volume_mm3,
                    "surface_area_mm2": validation.surface_area_mm2,
                    "triangle_count": validation.triangle_count,
                    "is_watertight": validation.is_watertight,
                },
            }

        asset.parsed_filament_grams = slicer_result.filament_grams
        asset.parsed_print_minutes = slicer_result.print_minutes
        cost_per_gram = _load_cost_settings()["cost_per_gram"]
        asset.parsed_material_cost = (
            slicer_result.filament_grams * cost_per_gram
        ).quantize(Decimal("0.01"))
        gcode_path = gcode_out

        if gcode_path and gcode_path.exists():
            try:
                prod_id = asset.related_product_id or 0
                var_id = asset.variant_id
                gcode_key = gcode_storage_key(
                    prod_id,
                    _preferred_gcode_filename(asset),
                    variant_id=var_id,
                )
                gcode_ref = upload_bytes_to_storage(
                    gcode_path.read_bytes(),
                    bucket=current_app.config.get("PRODUCT_ASSETS_BUCKET", "products"),
                    key=gcode_key,
                    local_root=current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products"),
                    content_type="text/plain",
                )
                asset.gcode_path = gcode_ref
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to upload G-code for asset %s: %s", asset.id, exc
                )

        asset.analysis_status = "complete"
        asset.analysis_completed_at = datetime.now(timezone.utc)
        _apply_initial_cost_snapshot(asset)

        db.session.commit()

        convert_task = convert_model_asset_for_viewer.delay(asset_id)

        return {
            "success": True,
            "asset_id": asset.id,
            "filament_grams": str(slicer_result.filament_grams),
            "print_minutes": str(slicer_result.print_minutes),
            "slicer_profile": slicer_result.profile_used,
            "validation": {
                "volume_mm3": validation.volume_mm3,
                "surface_area_mm2": validation.surface_area_mm2,
                "triangle_count": validation.triangle_count,
                "is_watertight": validation.is_watertight,
                "printer_fit": validation.printer_fit,
            },
            "convert_task_id": convert_task.id,
        }

    except Exception as exc:
        if asset is not None:
            asset.analysis_status = "failed"
            asset.analysis_error = str(exc)
            db.session.commit()
        raise analyze_model_asset.retry(exc=exc)

    finally:
        if work_dir and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)

        if gcode_path and gcode_path.exists():
            try:
                gcode_path.unlink()
            except Exception:
                pass


@celery.task(bind=True, max_retries=1)
def convert_model_asset_for_viewer(self, asset_id: int) -> dict:
    asset = db.session.get(ModelAsset, asset_id)
    if asset is None:
        return {"success": False, "error": "Asset not found"}

    try:
        file_location = asset.file_location
        if not file_location:
            return {"success": False, "error": "No file location"}

        ext = Path(file_location).suffix.lower()
        if ext == ".glb":
            asset.convert_status = "complete"
            asset.converted_model_path = file_location
            db.session.commit()
            return {"success": True, "converted_path": file_location}

        tmp_dir = Path(tempfile.mkdtemp(prefix="dfp-convert-"))
        data = download_storage_bytes(file_location)
        source_path = tmp_dir / f"source{ext}"
        source_path.write_bytes(data)

        output_path = tmp_dir / "converted.glb"
        converted = convert_to_glb(source_path, output_path)
        if converted is None:
            asset.convert_status = "failed"
            asset.conversion_error = "Conversion to GLB failed"
            db.session.commit()
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return {"success": False, "error": "Conversion failed"}

        bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
        local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")
        prod_id = asset.related_product_id or 0
        key = converted_storage_key(
            prod_id,
            _preferred_converted_filename(asset),
            variant_id=asset.variant_id,
        )

        storage_ref = upload_file_to_storage(
            output_path,
            bucket=bucket,
            key=key,
            local_root=local_root,
            content_type="model/gltf-binary",
        )

        shutil.rmtree(tmp_dir, ignore_errors=True)

        asset.convert_status = "complete"
        asset.converted_model_path = storage_ref
        db.session.commit()

        return {"success": True, "converted_path": storage_ref}

    except Exception as exc:
        asset.convert_status = "failed"
        asset.conversion_error = str(exc)
        db.session.commit()
        return {"success": False, "error": str(exc)}
