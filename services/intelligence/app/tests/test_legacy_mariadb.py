import pytest
from sqlalchemy import select

from app.models import LegacyMariaDbTableSnapshot
from app.schemas.imports import LegacyMariaDbInspectRequest
from app.services.legacy_mariadb import inspect_legacy_mariadb, resolve_legacy_config


def test_legacy_config_requires_read_only_connection_details(monkeypatch):
    monkeypatch.setattr("app.services.legacy_mariadb.settings.legacy_mariadb_host", None)
    with pytest.raises(ValueError, match="Missing legacy MariaDB connection settings"):
        resolve_legacy_config(LegacyMariaDbInspectRequest())


@pytest.mark.asyncio
async def test_legacy_schema_inspection_persists_snapshots(async_session):
    response = await inspect_legacy_mariadb(
        async_session,
        LegacyMariaDbInspectRequest(
            host="legacy.example.test",
            database="onlymyli_dudefishprinting",
            user="readonly",
            password="secret",
        ),
        schema_rows=[
            {
                "table_name": "products",
                "estimated_rows": 12,
                "columns": [
                    {"name": "id", "data_type": "int", "nullable": False, "key": "PRI"},
                    {"name": "name", "data_type": "varchar", "nullable": True, "key": ""},
                ],
                "primary_key_columns": ["id"],
            }
        ],
    )

    assert response.batch.status == "completed"
    assert response.batch.row_count == 1
    assert response.tables[0].table_name == "products"
    snapshots = (await async_session.execute(select(LegacyMariaDbTableSnapshot))).scalars().all()
    assert len(snapshots) == 1
    assert snapshots[0].primary_key_columns == ["id"]
