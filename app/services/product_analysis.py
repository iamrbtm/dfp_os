"""Race-proof analysis-run and model-asset management (Issues 6, 7, 27, 40).

The historical flow wrote analysis state directly onto the ``Product`` row.
If two uploads overlapped, the older task overwrote the newer task's fields.
This module replaces that with an explicit ``ProductAnalysisRun`` per attempt
plus ``ProductModelAsset`` rows for every uploaded/generated file. A task only
publishes its results to the ``Product`` summary fields while it remains the
*current* run for that product; otherwise it marks itself superseded and
leaves the product alone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.extensions import db
from app.models.catalog import (
    AnalysisRunStatus,
    AssetKind,
    Product,
    ProductAnalysisRun,
    ProductModelAsset,
)

# ---------------------------------------------------------------------------
# Issue 40 — bounded model_analysis_config schema
#
# Large blobs (slicer_results, geometry, embedded_settings_detected) no longer
# live on the Product row; they live on ProductAnalysisRun. Only scalar upload
# settings may be written to Product.model_analysis_config. Any key outside this
# set is stripped before the column is written.
MODEL_ANALYSIS_CONFIG_SCHEMA: frozenset[str] = frozenset(
    {
        "original_filename",
        "uploaded_at",
        "uploaded_by",
        "printer_profile",
        "material",
        "filament_density",
        "nozzle_diameter",
        "layer_height",
        "perimeters",
        "top_solid_layers",
        "bottom_solid_layers",
        "infill_percent",
        "infill_pattern",
        "supports",
        "brim_width",
        "copies",
        "scale_percent",
        "preserve_orientation",
        "multicolor",
        "use_embedded_settings",
        "embedded_settings_applied",
        "retain_gcode",
        "convert_to_glb",
    }
)


def sanitize_analysis_config(config: dict | None) -> dict:
    """Return only the allowed scalar keys (Issue 40)."""
    if not config:
        return {}
    return {key: value for key, value in config.items() if key in MODEL_ANALYSIS_CONFIG_SCHEMA}


# ---------------------------------------------------------------------------
# Issue 7 — stale-asset retention policy
#
# Keep stale assets for history by default; never auto-delete silently. The
# product studio may offer explicit deletion. This constant is the single
# source of truth for the retention rule so the UI and any cleanup job agree.
STALE_ASSET_RETENTION_DAYS = 30
STALE_ASSET_POLICY = "archive_after_retention"
ANALYSIS_LEASE_TIMEOUT = timedelta(minutes=15)
ACTIVE_ANALYSIS_STATES: frozenset[AnalysisRunStatus] = frozenset(
    {
        AnalysisRunStatus.STARTED,
        AnalysisRunStatus.VALIDATING,
        AnalysisRunStatus.SLICING,
        AnalysisRunStatus.STORING_GCODE,
        AnalysisRunStatus.COSTING,
        AnalysisRunStatus.CONVERTING,
    }
)
TERMINAL_ANALYSIS_STATES: frozenset[AnalysisRunStatus] = frozenset(
    {
        AnalysisRunStatus.COMPLETE,
        AnalysisRunStatus.FAILED,
        AnalysisRunStatus.SUPERSEDED,
    }
)


def stale_asset_age_days(asset: ProductModelAsset) -> int | None:
    if asset.is_current:
        return 0
    updated = asset.updated_at or asset.created_at
    if updated is None:
        return None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - updated).total_seconds() // 86400))


# ---------------------------------------------------------------------------
# Issue 6 — model assets
#


def create_model_asset(
    product: Product,
    *,
    storage_reference: str,
    original_filename: str,
    safe_filename: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    asset_kind: AssetKind,
    is_current: bool = True,
) -> ProductModelAsset:
    """Record one uploaded/generated file for a product.

    When a new source model or generated G-code is marked current, prior
    current assets of the same kind flip to ``is_current=False`` (Issue 7).
    Other asset kinds are not affected, so generating G-code never marks its
    source model stale.
    """
    if is_current and asset_kind in {AssetKind.SOURCE_MODEL, AssetKind.GCODE}:
        db.session.query(ProductModelAsset).filter(
            ProductModelAsset.product_id == product.id,
            ProductModelAsset.asset_kind == asset_kind,
            ProductModelAsset.is_current.is_(True),
        ).update({ProductModelAsset.is_current: False}, synchronize_session=False)

    asset = ProductModelAsset(
        product_id=product.id,
        business_id=product.business_id,
        storage_reference=storage_reference,
        original_filename=original_filename,
        safe_filename=safe_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        asset_kind=asset_kind,
        is_current=is_current,
    )
    db.session.add(asset)
    db.session.flush()
    return asset


def mark_asset_stale(asset: ProductModelAsset) -> None:
    asset.is_current = False
    db.session.add(asset)


def current_asset(product: Product, asset_kind: AssetKind) -> ProductModelAsset | None:
    return (
        db.session.query(ProductModelAsset)
        .filter(
            ProductModelAsset.product_id == product.id,
            ProductModelAsset.asset_kind == asset_kind,
            ProductModelAsset.is_current.is_(True),
        )
        .order_by(ProductModelAsset.created_at.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Issue 6 — analysis runs (race-proof)
#


def start_analysis_run(
    product: Product,
    *,
    source_asset: ProductModelAsset,
    requested_by_id: int | None = None,
    settings: dict | None = None,
    embedded_settings: dict | None = None,
    session: Any | None = None,
    product_locked: bool = False,
) -> ProductAnalysisRun:
    """Create a new current analysis run and supersede any prior current run.

    Called at enqueue time. The returned run's ``id`` is what the Celery task
    carries so it can later check "am I still current?" before writing.
    """
    session = session or db.session
    if not product_locked:
        locked_product = lock_product_for_analysis(product.id, session=session)
        if locked_product is None:
            raise ValueError("Product not found while starting analysis run")
        product = locked_product

    now = datetime.now(timezone.utc)
    session.query(ProductAnalysisRun).filter(
        ProductAnalysisRun.product_id == product.id,
        ProductAnalysisRun.is_current.is_(True),
    ).update(
        {
            ProductAnalysisRun.is_current: False,
            ProductAnalysisRun.status: AnalysisRunStatus.SUPERSEDED,
            ProductAnalysisRun.superseded_at: now,
        },
        synchronize_session=False,
    )
    run = ProductAnalysisRun(
        product_id=product.id,
        business_id=product.business_id,
        source_asset_id=source_asset.id,
        requested_by_id=requested_by_id,
        status=AnalysisRunStatus.QUEUED,
        is_current=True,
        requested_at=now,
        settings_json=settings,
        embedded_settings_json=embedded_settings,
    )
    session.add(run)
    session.flush()
    return run


def lock_product_for_analysis(
    product_id: int,
    *,
    session: Any | None = None,
) -> Product | None:
    """Serialize source-asset and run changes for one product."""
    session = session or db.session
    return (
        session.query(Product)
        .filter(Product.id == product_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )


def claim_analysis_run(
    product_id: int,
    run_id: int,
    *,
    session: Any | None = None,
    now: datetime | None = None,
    lease_timeout: timedelta = ANALYSIS_LEASE_TIMEOUT,
) -> ProductAnalysisRun | None:
    """Atomically claim one exact queued/current analysis run.

    A Celery redelivery or stale task returns ``None`` without changing either
    the run or product. A successful claim commits the STARTED transition
    before external work begins.
    """
    session = session or db.session
    now = now or datetime.now(timezone.utc)
    product = lock_product_for_analysis(product_id, session=session)
    if product is None:
        session.rollback()
        return None

    run = (
        session.query(ProductAnalysisRun)
        .filter(
            ProductAnalysisRun.id == run_id,
            ProductAnalysisRun.product_id == product_id,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    updated_at = run.updated_at if run is not None else None
    if updated_at is not None and updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    stale_active = bool(
        run
        and run.status in ACTIVE_ANALYSIS_STATES
        and updated_at is not None
        and updated_at <= now - lease_timeout
    )
    if (
        run is None
        or run.product_id != product_id
        or (run.status != AnalysisRunStatus.QUEUED and not stale_active)
        or not run.is_current
    ):
        session.rollback()
        return None

    run.status = AnalysisRunStatus.STARTED
    run.updated_at = now
    product.analysis_status = "analyzing"
    session.add(run)
    session.add(product)
    session.flush()
    session.commit()
    return run


def requeue_analysis_run(
    product_id: int,
    run_id: int,
    *,
    session: Any | None = None,
) -> bool:
    """Make one current nonterminal run claimable before a Celery retry."""
    session = session or db.session
    product = lock_product_for_analysis(product_id, session=session)
    if product is None:
        session.rollback()
        return False
    run = (
        session.query(ProductAnalysisRun)
        .filter(
            ProductAnalysisRun.id == run_id,
            ProductAnalysisRun.product_id == product_id,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if (
        run is None
        or not run.is_current
        or (run.status != AnalysisRunStatus.QUEUED and run.status not in ACTIVE_ANALYSIS_STATES)
    ):
        session.rollback()
        return False
    run.status = AnalysisRunStatus.QUEUED
    run.error = None
    run.completed_at = None
    product.analysis_status = "pending"
    product.analysis_error = None
    session.add(run)
    session.add(product)
    session.flush()
    session.commit()
    return True


def retire_current_gcode_assets(
    product: Product,
    *,
    session: Any | None = None,
) -> int:
    """Clear backward G-code state when a successful run retains no artifact."""
    session = session or db.session
    updated = (
        session.query(ProductModelAsset)
        .filter(
            ProductModelAsset.product_id == product.id,
            ProductModelAsset.asset_kind == AssetKind.GCODE,
            ProductModelAsset.is_current.is_(True),
        )
        .update(
            {ProductModelAsset.is_current: False},
            synchronize_session=False,
        )
    )
    product.gcode_path = None
    session.add(product)
    return updated


def lock_current_analysis_run_for_publish(
    product_id: int,
    run_id: int,
    *,
    session: Any | None = None,
) -> tuple[Product, ProductAnalysisRun] | None:
    """Lock product and exact run, then verify it is the sole current run."""
    session = session or db.session
    product = lock_product_for_analysis(product_id, session=session)
    if product is None:
        return None
    run = (
        session.query(ProductAnalysisRun)
        .filter(
            ProductAnalysisRun.id == run_id,
            ProductAnalysisRun.product_id == product_id,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    current_runs = (
        session.query(ProductAnalysisRun)
        .filter(
            ProductAnalysisRun.product_id == product_id,
            ProductAnalysisRun.is_current.is_(True),
        )
        .populate_existing()
        .with_for_update()
        .all()
    )
    if run is None or not run.is_current or len(current_runs) != 1 or current_runs[0].id != run_id:
        return None
    if run.status in TERMINAL_ANALYSIS_STATES:
        return None
    return product, run


def is_current_run(run_id: int, *, for_update: bool = False) -> bool:
    if for_update:
        run = (
            db.session.query(ProductAnalysisRun)
            .filter(ProductAnalysisRun.id == run_id)
            .populate_existing()
            .with_for_update()
            .one_or_none()
        )
    else:
        run = db.session.get(ProductAnalysisRun, run_id)
    return bool(run and run.is_current)


def get_current_run(product: Product) -> ProductAnalysisRun | None:
    return (
        db.session.query(ProductAnalysisRun)
        .filter(
            ProductAnalysisRun.product_id == product.id,
            ProductAnalysisRun.is_current.is_(True),
        )
        .order_by(ProductAnalysisRun.created_at.desc())
        .first()
    )


def set_run_status(run: ProductAnalysisRun, status: AnalysisRunStatus) -> None:
    run.status = status
    if status in (
        AnalysisRunStatus.COMPLETE,
        AnalysisRunStatus.FAILED,
        AnalysisRunStatus.SUPERSEDED,
    ):
        if run.completed_at is None:
            run.completed_at = datetime.now(timezone.utc)
    db.session.add(run)


def publish_run_results(
    run: ProductAnalysisRun,
    product: Product,
    *,
    geometry: dict | None = None,
    slicer_stats: dict | None = None,
    parsed_volume_mm3: Decimal | None = None,
    parsed_surface_area_mm2: Decimal | None = None,
    parsed_triangle_count: int | None = None,
    parsed_filament_grams: Decimal | None = None,
    parsed_print_minutes: Decimal | None = None,
    parsed_material_cost: Decimal | None = None,
    gcode_asset_id: int | None = None,
    preview_asset_id: int | None = None,
    metadata_asset_id: int | None = None,
    error: str | None = None,
    session: Any | None = None,
    already_locked: bool = False,
) -> bool:
    """Copy run summary fields onto the Product row ONLY if still current.

    Returns ``True`` if the product was updated, ``False`` if the run was
    superseded by a newer upload and must not touch the product (Issue 6).
    """
    session = session or db.session
    if not already_locked:
        locked = lock_current_analysis_run_for_publish(
            product.id,
            run.id,
            session=session,
        )
        if locked is None:
            return False
        product, run = locked

    if not run.is_current:
        run.status = AnalysisRunStatus.SUPERSEDED
        if run.superseded_at is None:
            run.superseded_at = datetime.now(timezone.utc)
        if run.completed_at is None:
            run.completed_at = run.superseded_at
        session.add(run)
        return False

    if run.status in TERMINAL_ANALYSIS_STATES:
        return False

    if geometry is not None:
        run.geometry_json = geometry
    if slicer_stats is not None:
        run.slicer_stats_json = slicer_stats
    run.parsed_volume_mm3 = parsed_volume_mm3
    run.parsed_surface_area_mm2 = parsed_surface_area_mm2
    run.parsed_triangle_count = parsed_triangle_count
    run.parsed_filament_grams = parsed_filament_grams
    run.parsed_print_minutes = parsed_print_minutes
    run.parsed_material_cost = parsed_material_cost
    if gcode_asset_id is not None:
        run.gcode_asset_id = gcode_asset_id
    if preview_asset_id is not None:
        run.preview_asset_id = preview_asset_id
    if metadata_asset_id is not None:
        run.metadata_asset_id = metadata_asset_id
    run.error = error

    if error:
        run.status = AnalysisRunStatus.FAILED
        run.completed_at = datetime.now(timezone.utc)
        product.analysis_status = "failed"
        product.analysis_error = error
    else:
        run.status = AnalysisRunStatus.COMPLETE
        run.completed_at = datetime.now(timezone.utc)
        # These are summary fields copied from the latest current run. In most
        # cases do not write to them directly — write to the run instead.
        product.analysis_status = "complete"
        product.analysis_error = None
        product.parsed_volume_mm3 = parsed_volume_mm3
        product.parsed_surface_area_mm2 = parsed_surface_area_mm2
        product.parsed_triangle_count = parsed_triangle_count
        product.parsed_filament_grams = parsed_filament_grams
        product.parsed_print_minutes = parsed_print_minutes
        product.parsed_material_cost = parsed_material_cost
        product.analysis_completed_at = run.completed_at
    session.add(run)
    return True


# ---------------------------------------------------------------------------
# Issue 27 — re-analyze must reset stale cost/analysis fields
#


ANALYSIS_SUMMARY_FIELDS: tuple[str, ...] = (
    "parsed_filament_grams",
    "parsed_print_minutes",
    "parsed_material_cost",
    "parsed_volume_mm3",
    "parsed_surface_area_mm2",
    "parsed_triangle_count",
    "estimated_material_cost",
    "estimated_profit",
    "estimated_print_minutes",
    "gcode_path",
    "converted_model_path",
    "convert_status",
    "conversion_error",
    "model_metadata_path",
)


def reset_product_analysis(product: Product, *, keep_status_pending: bool = True) -> None:
    """Clear stale analysis/cost fields before a new run overwrites them."""
    for field in ANALYSIS_SUMMARY_FIELDS:
        setattr(product, field, None)
    product.analysis_error = None
    product.analysis_completed_at = None
    product.analysis_requested_at = datetime.now(timezone.utc)
    if keep_status_pending:
        product.analysis_status = "pending"


def is_analysis_in_progress(product: Product) -> bool:
    return product.analysis_status in {"pending", "analyzing", "slicing", "validating"}


__all__ = [
    "MODEL_ANALYSIS_CONFIG_SCHEMA",
    "ACTIVE_ANALYSIS_STATES",
    "TERMINAL_ANALYSIS_STATES",
    "STALE_ASSET_RETENTION_DAYS",
    "STALE_ASSET_POLICY",
    "ANALYSIS_SUMMARY_FIELDS",
    "sanitize_analysis_config",
    "stale_asset_age_days",
    "create_model_asset",
    "mark_asset_stale",
    "current_asset",
    "start_analysis_run",
    "lock_product_for_analysis",
    "claim_analysis_run",
    "requeue_analysis_run",
    "retire_current_gcode_assets",
    "lock_current_analysis_run_for_publish",
    "is_current_run",
    "get_current_run",
    "set_run_status",
    "publish_run_results",
    "reset_product_analysis",
    "is_analysis_in_progress",
]
