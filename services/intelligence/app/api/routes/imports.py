from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.imports import LegacyMariaDbInspectRequest, LegacyMariaDbInspectResponse, SquareImportResponse
from app.security import verify_internal_token
from app.services.legacy_mariadb import inspect_legacy_mariadb
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


@router.post("/legacy-mariadb/inspect", response_model=LegacyMariaDbInspectResponse, status_code=status.HTTP_201_CREATED)
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
