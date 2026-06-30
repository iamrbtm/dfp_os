from __future__ import annotations

import time as time_module
import xml.etree.ElementTree as ET
from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import ScoutResult, build_xml_headers

HOT_ITEMS_URL = "https://boardgamegeek.com/xmlapi2/hot"
SEARCH_URL = "https://boardgamegeek.com/xmlapi2/search"

HOT_CATEGORIES = ["boardgame", "boardgameexpansion", "boardgameaccessory"]

SEED_QUERIES = [
    "3D printed insert",
    "board game organizer",
    "board game token",
    "board game upgrade",
    "board game box",
    "card holder",
    "dice tower",
    "dice tray",
    "miniature storage",
    "board game shelf",
]

MAX_RETRIES = 3
RETRY_DELAY = 2.0


def _fetch_xml(
    session: requests.Session,
    url: str,
    params: dict[str, str],
    limiter: Any,
) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    for attempt in range(MAX_RETRIES):
        limiter.wait()
        headers = build_xml_headers()
        try:
            resp = session.get(url, params=params, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.text, errors
            if resp.status_code == 202:
                # BGG returns 202 when data is being generated/cached
                time_module.sleep(RETRY_DELAY * (attempt + 1))
                continue
            if resp.status_code == 429:
                # Rate limited - back off
                time_module.sleep(RETRY_DELAY * 3 * (attempt + 1))
                continue
            errors.append(f"HTTP {resp.status_code}")
            return None, errors
        except requests.RequestException as e:
            errors.append(str(e))
            if attempt < MAX_RETRIES - 1:
                time_module.sleep(RETRY_DELAY * (attempt + 1))
    return None, errors


def fetch_hot_items(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []

    for category in HOT_CATEGORIES:
        result = ScoutResult(source="bgg", keyword_or_category=f"hot_{category}")
        xml_text, errors = _fetch_xml(session, HOT_ITEMS_URL, {"type": category}, limiter)
        if xml_text is None:
            result.errors = errors
            results.append(result)
            continue

        try:
            root = ET.fromstring(xml_text)
            for item_el in root.findall("item"):
                name_el = item_el.find("name")
                year_el = item_el.find("yearpublished")
                result.items.append(
                    {
                        "id": item_el.get("id"),
                        "title": name_el.get("value") if name_el is not None else "",
                        "year_published": year_el.get("value") if year_el is not None else None,
                        "rank": int(item_el.get("rank", 0)) if item_el.get("rank") else None,
                        "thumbnail": item_el.get("thumbnail", ""),
                        "type": category,
                    }
                )
            result.metadata["total_results"] = len(result.items)
            result.metadata["category"] = category
            result.errors = errors
        except ET.ParseError as e:
            result.errors.append(f"XML parse error: {e}")

        results.append(result)

    for query in SEED_QUERIES:
        result = ScoutResult(source="bgg", keyword_or_category=query)
        xml_text, errors = _fetch_xml(
            session,
            SEARCH_URL,
            {"query": query, "type": "boardgameaccessory"},
            limiter,
        )
        if xml_text is None:
            result.errors = errors
            results.append(result)
            continue

        try:
            root = ET.fromstring(xml_text)
            for item_el in root.findall("item"):
                name_el = item_el.find("name")
                year_el = item_el.find("yearpublished")
                result.items.append(
                    {
                        "id": item_el.get("id"),
                        "title": name_el.get("value") if name_el is not None else "",
                        "year_published": year_el.get("value") if year_el is not None else None,
                        "type": item_el.get("type"),
                    }
                )
            result.metadata["total_results"] = len(result.items)
            result.metadata["query"] = query
            result.errors = errors
        except ET.ParseError as e:
            result.errors.append(f"XML parse error: {e}")

        results.append(result)

    return results
