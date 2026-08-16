from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.market_catalog_importers import tennesseefairs as _tennesseefairs


@dataclass
class ImporterInfo:
    key: str
    name: str
    description: str
    source_urls: list[str]
    # The site module: exposes KEY/NAME/DESCRIPTION/SOURCE_URLS, parse_pages(pages),
    # and build_payload(record). All fetch/parse logic lives there.
    module: Any


IMPORTERS: dict[str, ImporterInfo] = {
    "tennesseefairs": ImporterInfo(
        key="tennesseefairs",
        name=_tennesseefairs.NAME,
        description=_tennesseefairs.DESCRIPTION,
        source_urls=list(_tennesseefairs.SOURCE_URLS),
        module=_tennesseefairs,
    ),
}

# Stable display order for the import modal.
_IMPORTER_ORDER = ("tennesseefairs",)


def list_importers() -> list[ImporterInfo]:
    return [IMPORTERS[key] for key in _IMPORTER_ORDER if key in IMPORTERS]


def get_importer(key: str) -> ImporterInfo | None:
    return IMPORTERS.get(key)


def get_importer_module(key: str):
    info = IMPORTERS.get(key)
    return info.module if info else None


def run_importer(
    key: str, *, dry_run: bool = True, actor: Any | None = None, client: Any | None = None
) -> dict:
    """Dispatch to the shared runner, which handles fetch/schema/dedup/persist."""
    from app.services.market_catalog_importers.runner import run_import

    return run_import(key=key, dry_run=dry_run, actor=actor, client=client)
