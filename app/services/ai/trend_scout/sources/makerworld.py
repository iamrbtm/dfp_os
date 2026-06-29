from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.ai.trend_scout.sources._base import ScoutResult

logger = logging.getLogger(__name__)

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

BASE_URL = "https://makerworld.com"

CATEGORIES: dict[str, str] = {
    "all": "",
    "3d-printer": "900-3d-printer",
    "art": "100-art",
    "education": "500-education",
    "fashion": "200-fashion",
    "hobby-diy": "300-hobby-and-diy",
    "household": "400-household",
    "miniatures": "600-miniatures",
    "props-cosplays": "1000-props-and-cosplays",
    "tools": "700-tools",
    "toys-games": "800-toys-and-games",
    "generative": "2000-generative-3d-model",
}

SORTS = ["hotScore", "downloadCount", "likeCount"]

HOT_CATEGORIES = [
    "toys-games",
    "household",
    "tools",
    "miniatures",
    "art",
    "hobby-diy",
    "fashion",
    "props-cosplays",
    "3d-printer",
]

def _design_to_item(d: dict, category_slug: str, sort: str) -> dict[str, Any]:
    creator = d.get("designCreator") or {}
    designer_name = creator.get("name", "") if isinstance(creator, dict) else ""
    return {
        "id": d.get("id", ""),
        "title": d.get("title", ""),
        "url": f"{BASE_URL}/en/models/{d.get('id', '')}-{d.get('slug', '')}",
        "thumbnail": d.get("cover", ""),
        "designer": designer_name,
        "likes": d.get("likeCount", 0),
        "downloads": d.get("downloadCount", 0),
        "prints_count": d.get("printCount", 0),
        "collections": d.get("collectionCount", 0),
        "nsfw": d.get("nsfw", False),
        "category": category_slug or "all",
        "sort": sort,
    }


def _extract_designs(page_props: dict) -> list[dict]:
    for key in page_props:
        val = page_props[key]
        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict) and "id" in val[0]:
            return val
    return []


def _parse_browse_page(text: str, category_slug: str, sort: str, max_items: int) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    items: list[dict[str, Any]] = []

    match = re.search(r"__NEXT_DATA__[^>]+>(.*?)</", text)
    if not match:
        return items, ["__NEXT_DATA__ not found in page"]

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        return items, [f"JSON parse error: {e}"]

    page_props = data.get("props", {}).get("pageProps", {})
    designs = _extract_designs(page_props)

    for d in designs[:max_items]:
        items.append(_design_to_item(d, category_slug, sort))

    if not items and not errors:
        errors.append("No design data found in page")

    return items, errors


def _parse_main_page(text: str, max_items: int) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    items: list[dict[str, Any]] = []

    match = re.search(r"__NEXT_DATA__[^>]+>(.*?)</", text)
    if not match:
        return items, ["__NEXT_DATA__ not found in page"]

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        return items, [f"JSON parse error: {e}"]

    v2_props = data.get("props", {}).get("pageProps", {}).get("v2Props", {})
    hits = v2_props.get("foryouData", {}).get("hits", [])

    for hit in hits:
        if hit.get("type") == 0 and "design" in hit:
            d = hit["design"].copy()
            raw_id = d.get("id", "")
            if isinstance(raw_id, str) and "_" in raw_id:
                d["id"] = raw_id.split("_", 1)[0]
            items.append(_design_to_item(d, "main", "featured"))

    items = items[:max_items]

    if not items and not errors:
        errors.append("No design data found in main page")

    return items, errors


def _fetch_scrape_result(
    url: str, category_slug: str, sort: str, max_items: int, *, use_main_parser: bool = False
) -> ScoutResult:
    if not HAS_CURL_CFFI:
        return ScoutResult(
            source="makerworld",
            keyword_or_category=category_slug or sort,
            errors=["curl_cffi not installed"],
        )

    try:
        resp = curl_requests.get(url, impersonate="chrome131", timeout=30)
        if resp.status_code != 200:
            return ScoutResult(
                source="makerworld",
                keyword_or_category=category_slug or sort,
                errors=[f"HTTP {resp.status_code}"],
            )
    except Exception as e:
        return ScoutResult(
            source="makerworld",
            keyword_or_category=category_slug or sort,
            errors=[str(e)],
        )

    if use_main_parser:
        items, errs = _parse_main_page(resp.text, max_items)
    else:
        items, errs = _parse_browse_page(resp.text, category_slug, sort, max_items)

    return ScoutResult(
        source="makerworld",
        keyword_or_category=category_slug or sort,
        items=items,
        errors=errs,
        metadata={"total_results": len(items), "sort": sort, "category": category_slug},
    )


def fetch_trending(session: Any, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []

    if not HAS_CURL_CFFI:
        results.append(
            ScoutResult(source="makerworld", keyword_or_category="init_error", errors=["curl_cffi not installed"])
        )
        return results

    # 1. Main page — personalised / for-you feed (38 design items)
    limiter.wait()
    r = _fetch_scrape_result(f"{BASE_URL}/en", "main", "featured", 38, use_main_parser=True)
    results.append(r)

    # 2. Global sorts — hot, downloads, likes across all categories
    for sort in SORTS:
        limiter.wait()
        r = _fetch_scrape_result(f"{BASE_URL}/en/3d-models?orderBy={sort}&page=1", "all", sort, 30)
        results.append(r)

    # 3. Category pages — hot items per category
    for slug_key in HOT_CATEGORIES:
        limiter.wait()
        cat_slug = CATEGORIES[slug_key]
        url = f"{BASE_URL}/en/3d-models/{cat_slug}?orderBy=hotScore&page=1" if cat_slug else f"{BASE_URL}/en/3d-models?orderBy=hotScore&page=1"
        r = _fetch_scrape_result(url, slug_key, "hotScore", 15)
        results.append(r)

    return results
