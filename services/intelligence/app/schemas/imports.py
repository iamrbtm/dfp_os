from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    status: str
    source_name: str | None
    source_fingerprint: str | None
    row_count: int
    error_count: int
    error_message: str | None


class SquareImportResponse(BaseModel):
    batch: ImportBatchResponse
    imported_rows: int
    rejected_rows: int
    sensitive_fields_removed: list[str]


class LegacyMariaDbInspectRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    database: str | None = None
    user: str | None = None
    password: str | None = None
    connect_timeout: int | None = Field(default=None, ge=1, le=60)


class LegacyMariaDbTableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    table_name: str
    estimated_rows: int | None
    columns: list[dict]
    primary_key_columns: list[str] | None


class LegacyMariaDbInspectResponse(BaseModel):
    batch: ImportBatchResponse
    tables: list[LegacyMariaDbTableResponse]


class LegacyImportAllRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    database: str | None = None
    user: str | None = None
    password: str | None = None
    connect_timeout: int | None = Field(default=None, ge=1, le=60)
    batch_size: int = Field(default=500, ge=100, le=10000)
    max_tables: int | None = Field(default=None, ge=1, le=500)


class LegacyTableManifestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    import_batch_id: str
    table_name: str
    estimated_row_count: int | None
    actual_row_count: int
    error_count: int
    error_message: str | None
    columns: list[dict]
    primary_key_columns: list[str] | None
    import_started_at: datetime | None
    import_completed_at: datetime | None
    created_at: datetime


class LegacyImportAllResponse(BaseModel):
    batch: ImportBatchResponse
    manifests: list[LegacyTableManifestResponse]


class LegacyTableReviewStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    table_name: str
    decision: str
    notes: str | None
    decided_by: str | None
    decided_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LegacyTableReviewRequest(BaseModel):
    decision: str = Field(..., pattern=r"^(keep|exclude|delete_staging)$")
    notes: str | None = None
    decided_by: str | None = None
    confirm_delete: bool = False


class LegacyTableReviewResponse(BaseModel):
    review: LegacyTableReviewStateResponse
    manifest: LegacyTableManifestResponse | None = None
    row_count: int = 0


class LegacyTableWithReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    table_name: str
    estimated_row_count: int | None
    actual_row_count: int | None
    error_count: int | None
    columns: list[dict] | None
    primary_key_columns: list[str] | None
    import_batch_id: str | None
    manifest_id: str | None
    review_id: str | None
    review_decision: str | None
    review_notes: str | None
    staged_row_count: int = 0


class LegacyTableListResponse(BaseModel):
    tables: list[LegacyTableWithReviewResponse]
    total_tables: int


class LegacyTableDeleteResponse(BaseModel):
    table_name: str
    rows_deleted: int
    review_reset: bool


class LegacyJsonExportTable(BaseModel):
    table_name: str
    estimated_rows: int | None = None
    primary_key_columns: list[str] | None = None
    columns: list[dict]
    rows: list[dict] = []


class LegacyJsonExportFile(BaseModel):
    source_name: str
    exported_at: str | None = None
    tables: list[LegacyJsonExportTable]


class LegacyJsonUploadResponse(BaseModel):
    batch: ImportBatchResponse
    manifests: list[LegacyTableManifestResponse]
    total_rows: int


class LegacyPromotedTableResult(BaseModel):
    table_name: str
    status: str
    entity_type: str | None = None
    row_count: int | None = None


class LegacyPromoteResponse(BaseModel):
    promoted: int
    skipped: int
    tables: list[LegacyPromotedTableResult]


class LegacyPromotedTableInfo(BaseModel):
    id: str
    table_name: str
    target_entity_type: str
    row_count: int
    column_names: list[str]
    promoted_at: str | None
