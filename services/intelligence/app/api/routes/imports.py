from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import LegacyTableReviewState
from app.schemas.imports import (
    LegacyImportAllRequest,
    LegacyImportAllResponse,
    LegacyJsonExportFile,
    LegacyJsonUploadResponse,
    LegacyMariaDbInspectRequest,
    LegacyMariaDbInspectResponse,
    LegacyPromotedTableInfo,
    LegacyPromoteResponse,
    LegacyTableDeleteResponse,
    LegacyTableListResponse,
    LegacyTableReviewRequest,
    LegacyTableReviewResponse,
    LegacyTableReviewStateResponse,
    SquareImportResponse,
)
from app.security import verify_internal_token
from app.services.legacy_mariadb import (
    delete_table_staging,
    import_all_legacy_tables,
    import_legacy_json_export,
    inspect_legacy_mariadb,
    list_imported_tables,
    review_table,
)
from app.services.legacy_promotion import list_promoted_tables, promote_kept_tables
from app.services.square_import import REQUIRED_SQUARE_COLUMNS, import_square_items_csv

router = APIRouter(prefix="/imports", tags=["imports"], dependencies=[Depends(verify_internal_token)])


@router.post("/square/items-csv", response_model=SquareImportResponse, status_code=status.HTTP_201_CREATED)
async def import_square_items(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_file_type", "message": "Square item imports must be CSV files."},
        )
    content = await file.read()
    try:
        return await import_square_items_csv(db, content, source_name=file.filename)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_square_csv",
                "message": str(exc),
                "required_columns": sorted(REQUIRED_SQUARE_COLUMNS),
            },
        ) from exc


@router.post(
    "/legacy-mariadb/inspect",
    response_model=LegacyMariaDbInspectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def inspect_legacy_database(
    payload: LegacyMariaDbInspectRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await inspect_legacy_mariadb(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "legacy_mariadb_config_missing", "message": str(exc)},
        ) from exc


@router.post(
    "/legacy-mariadb/upload-json",
    response_model=LegacyJsonUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_legacy_json(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_file_type", "message": "Legacy export must be a JSON file."},
        )
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "file_too_large", "message": "Legacy export file exceeds 100 MB limit."},
        )
    try:
        import json

        raw = json.loads(content)
        return await import_legacy_json_export(db, LegacyJsonExportFile.model_validate(raw))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_json", "message": f"File is not valid JSON: {exc}"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_export", "message": str(exc)},
        ) from exc


@router.post("/legacy-mariadb/import-all", response_model=LegacyImportAllResponse, status_code=status.HTTP_201_CREATED)
async def import_all_legacy(
    payload: LegacyImportAllRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await import_all_legacy_tables(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "legacy_mariadb_config_missing", "message": str(exc)},
        ) from exc


@router.get("/legacy-mariadb/tables", response_model=LegacyTableListResponse)
async def list_legacy_tables(
    db: AsyncSession = Depends(get_db),
):
    return await list_imported_tables(db)


@router.get("/legacy-mariadb/tables/{table_name}/review", response_model=LegacyTableReviewStateResponse)
async def get_table_review(
    table_name: str,
    db: AsyncSession = Depends(get_db),
):
    review = await db.execute(
        select(LegacyTableReviewState).where(LegacyTableReviewState.table_name == table_name)
    )
    review = review.scalar_one_or_none()
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "review_not_found", "message": f"No review found for table '{table_name}'."},
        )
    return LegacyTableReviewStateResponse.model_validate(review)


@router.post("/legacy-mariadb/tables/{table_name}/review", response_model=LegacyTableReviewResponse)
async def review_legacy_table(
    table_name: str,
    payload: LegacyTableReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await review_table(db, table_name, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "review_failed", "message": str(exc)},
        ) from exc


@router.post("/legacy-mariadb/promote", response_model=LegacyPromoteResponse, status_code=status.HTTP_200_OK)
async def promote_legacy_tables(
    db: AsyncSession = Depends(get_db),
):
    return await promote_kept_tables(db)


@router.get("/legacy-mariadb/promoted", response_model=list[LegacyPromotedTableInfo])
async def list_promoted_legacy_tables(
    db: AsyncSession = Depends(get_db),
):
    return await list_promoted_tables(db)


@router.delete("/legacy-mariadb/tables/{table_name}/staging", response_model=LegacyTableDeleteResponse)
async def delete_table_staging_endpoint(
    table_name: str,
    confirm: bool = False,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await delete_table_staging(db, table_name, confirm=confirm)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "delete_failed", "message": str(exc)},
        ) from exc


@router.post("/legacy-mariadb/cleanup-staging")
async def cleanup_legacy_staging(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text

    rows_stage = await db.execute(text("SELECT COUNT(*) FROM legacy_import_row_stage"))
    row_count = rows_stage.scalar() or 0
    manifest_count_row = await db.execute(text("SELECT COUNT(*) FROM legacy_table_manifests"))
    manifest_count = manifest_count_row.scalar() or 0

    await db.execute(text("DELETE FROM legacy_import_row_stage"))
    await db.execute(text("DELETE FROM legacy_table_manifests"))
    await db.execute(text("DELETE FROM legacy_table_review_state"))
    await db.commit()

    return {
        "rows_deleted": row_count,
        "manifests_deleted": manifest_count,
        "reviews_reset": manifest_count,
        "status": "staging_cleaned",
    }
