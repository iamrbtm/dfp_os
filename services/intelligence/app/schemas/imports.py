from __future__ import annotations

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
