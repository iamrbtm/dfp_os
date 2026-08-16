from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from urllib.parse import urlparse

from app.extensions import db
from app.models import MarketCatalogListing
from app.services.market_catalog import create_listing
from app.services.market_catalog_import import extraction_to_listing_fields
from app.schemas.market_catalog_import import SCHEMA_VERSION, validate as validate_import
from app.services.market_catalog_importers.registry import get_importer_module
from app.services.market_catalog_importers.util import _normalize_key, extract_county


def _host_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _is_duplicate(
    entry: dict[str, Any],
    loc: dict[str, Any],
    by_name: dict[str, int],
    by_host: dict[str, int],
    by_county_state: dict[tuple[str, str], int],
) -> bool:
    """Cross-source dedup: match an existing listing by name, website host, or county+state.

    Name and host are exact (normalized) keys. County+state only applies when the
    name looks like an event (fair/festival/market/...) to avoid merging unrelated
    records that merely share a county.
    """
    if _normalize_key(entry["name"]) in by_name:
        return True
    host = _host_of(entry.get("website_url"))
    if host and host in by_host:
        return True
    county = extract_county(entry["name"])
    state = (loc.get("state") or "TN").upper()
    if county and state and (county.lower(), state) in by_county_state:
        if re.search(r"fair|festival|market|expo|show|craft", entry["name"], re.I):
            return True
    return False


def run_import(
    *,
    key: str,
    dry_run: bool = True,
    actor: Any | None = None,
    client: Any | None = None,
    pages: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Shared import orchestration for any registered market/event site.

    The site module supplies only fetch targets (``SOURCE_URLS``) and parsing
    (``parse_pages`` / ``build_payload``). Everything else — Firecrawl fetch,
    schema verification, dedup, and persistence — lives here so it is shared across
    every importer.
    """
    module = get_importer_module(key)
    if module is None:
        raise KeyError(f"Unknown market catalog importer: {key}")

    if pages is None:
        if client is None:
            try:
                from flask import current_app

                from app.services.firecrawl_client import FirecrawlClient

                cfg = current_app.config
                base_url = cfg.get("FIRECRAWL_API_URL", os.getenv("FIRECRAWL_API_URL", "http://localhost:9500"))
                api_key = cfg.get("FIRECRAWL_API_KEY", os.getenv("FIRECRAWL_API_KEY", ""))
                timeout = float(cfg.get("FIRECRAWL_TIMEOUT_SECONDS", os.getenv("FIRECRAWL_TIMEOUT_SECONDS", "30")))
            except Exception:
                base_url = api_key = None
                timeout = None
            client = FirecrawlClient(base_url=base_url, api_key=api_key, timeout_seconds=timeout)
        pages = module.fetch_pages(client)

    parsed = module.parse_pages(pages)
    records = parsed.get("records", []) if isinstance(parsed, dict) else parsed
    calendar_count = parsed.get("counts", {}).get("calendar", 0) if isinstance(parsed, dict) else 0
    directory_count = parsed.get("counts", {}).get("directory", 0) if isinstance(parsed, dict) else 0

    entries = [module.build_payload(r) for r in records]

    import_doc = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": module.NAME,
            "url": module.SOURCE_URLS[0] if module.SOURCE_URLS else "",
            "page_title": module.NAME,
            "scraped_at": datetime.now(timezone.utc),
            "scraper": key,
            "query_or_context": "; ".join(module.SOURCE_URLS),
        },
        "entries": entries,
        "errors": [],
    }
    schema_valid = True
    schema_error: str | None = None
    try:
        validate_import(import_doc, strict=True)
    except Exception as exc:  # contract break: surface, do not silently persist
        schema_valid = False
        schema_error = str(exc)

    summary: dict[str, Any] = {
        "key": key,
        "calendar_count": calendar_count,
        "directory_count": directory_count,
        "merged_count": len(records),
        "created": 0,
        "skipped": 0,
        "errors": [],
        "dry_run": dry_run,
        "schema_valid": schema_valid,
        "schema_error": schema_error,
        "preview": [],
    }

    if not dry_run and not schema_valid:
        summary["errors"].append(
            {"name": "<import_schema>", "error": schema_error or "import document failed schema validation"}
        )
        return summary

    by_name: dict[str, int] = {}
    by_host: dict[str, int] = {}
    by_county_state: dict[tuple[str, str], int] = {}
    if not dry_run:
        for row in (
            db.session.query(MarketCatalogListing)
            .filter(MarketCatalogListing.deleted_at.is_(None))
            .all()
        ):
            by_name[_normalize_key(row.name)] = row.id
            host = _host_of(row.website_url)
            if host:
                by_host[host] = row.id
            county = extract_county(row.name)
            state = (row.state or "").upper()
            if county and state:
                by_county_state[(county.lower(), state)] = row.id

    for entry in entries:
        loc = entry.get("location") or {}
        tim = entry.get("timing") or {}
        org = entry.get("organizer") or {}
        summary["preview"].append(
            {
                "name": entry["name"],
                "website_url": entry.get("website_url"),
                "city": loc.get("city"),
                "state": loc.get("state"),
                "anchor_date": tim.get("anchor_date"),
                "has_contact": bool(org.get("email")),
            }
        )
        if dry_run:
            continue
        try:
            fields, tiers = extraction_to_listing_fields(entry)
            if _is_duplicate(entry, loc, by_name, by_host, by_county_state):
                summary["skipped"] += 1
                continue
            listing = create_listing(actor=actor, tiers=tiers, **fields)
            summary["created"] += 1
            by_name[_normalize_key(entry["name"])] = listing.id
            host = _host_of(entry.get("website_url"))
            if host:
                by_host[host] = listing.id
            county = extract_county(entry["name"])
            state = (loc.get("state") or "TN").upper()
            if county and state:
                by_county_state[(county.lower(), state)] = listing.id
        except Exception as exc:  # surface per-row failures without aborting the run
            summary["errors"].append({"name": entry["name"], "error": str(exc)})

    return summary
