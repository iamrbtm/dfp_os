from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import current_app

from app.models.catalog import Product
from app.services.storage import (
    download_storage_bytes,
    metadata_storage_key,
    storage_reference_name,
    upload_bytes_to_storage,
)

SCHEMA_VERSION = "1.0"


def _decimal_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def build_model_metadata(product: Product, *, source_bytes: bytes | None = None) -> dict:
    source = product.model_file_path
    if source_bytes is None and source:
        try:
            source_bytes = download_storage_bytes(source)
        except Exception:
            source_bytes = None

    config = dict(product.model_analysis_config or {})
    return {
        "schema": "dfpos.model-asset-metadata",
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "business_id": product.business_id,
        "product": {"id": product.id, "name": product.name, "sku": product.sku_base},
        "source": {
            "filename": config.get("original_filename") or storage_reference_name(source),
            "reference": source,
            "size_bytes": len(source_bytes) if source_bytes is not None else None,
            "sha256": (
                hashlib.sha256(source_bytes).hexdigest() if source_bytes is not None else None
            ),
            "uploaded_at": config.get("uploaded_at"),
            "uploaded_by": config.get("uploaded_by"),
        },
        "slicer": config,
        "geometry": {
            "volume_mm3": _decimal_string(product.parsed_volume_mm3),
            "surface_area_mm2": _decimal_string(product.parsed_surface_area_mm2),
            "triangle_count": product.parsed_triangle_count,
            **dict(config.get("geometry") or {}),
        },
        "results": {
            "filament_grams": _decimal_string(product.parsed_filament_grams),
            "print_minutes": _decimal_string(product.parsed_print_minutes),
            "material_cost": _decimal_string(product.parsed_material_cost),
        },
        "derived_assets": {
            "gcode": product.gcode_path,
            "glb": product.converted_model_path,
            "glb_requested": product.model_convert_to_glb,
        },
        "status": {
            "analysis": product.analysis_status,
            "analysis_error": product.analysis_error,
            "conversion": product.convert_status,
            "conversion_error": product.conversion_error,
            "requested_at": (
                product.analysis_requested_at.isoformat() if product.analysis_requested_at else None
            ),
            "completed_at": (
                product.analysis_completed_at.isoformat() if product.analysis_completed_at else None
            ),
        },
    }


def write_model_metadata(product: Product, *, source_bytes: bytes | None = None) -> str:
    payload = build_model_metadata(product, source_bytes=source_bytes)
    filename = (
        f"{Path(storage_reference_name(product.model_file_path)).stem or 'model'}.metadata.json"
    )
    reference = upload_bytes_to_storage(
        json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
        bucket=current_app.config.get("PRODUCT_ASSETS_BUCKET", "products"),
        key=metadata_storage_key(product.id, filename),
        local_root=current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products"),
        content_type="application/json",
    )
    product.model_metadata_path = reference
    return reference


def read_model_metadata(product: Product) -> dict:
    if not product.model_metadata_path:
        return build_model_metadata(product)
    try:
        return json.loads(download_storage_bytes(product.model_metadata_path))
    except OSError, ValueError, TypeError:
        return build_model_metadata(product)
