from __future__ import annotations

from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import (
    ScoutResult,
    build_browser_headers,
)

BASE_URL = "https://www.myminifactory.com"
SEARCH_API = f"{BASE_URL}/api/search"

SEED_QUERIES = [
    "dragon",
    "articulated dragon",
    "flexi animal",
    "fidget",
    "board game insert",
    "gridfinity",
    "cosplay prop",
    "miniature",
    "desk organizer",
    "phone stand",
    "lamp",
    "vase",
    "earrings",
    "keychain",
    "planter",
    "bookend",
]


def extract_item(item: dict) -> dict:
    title = item.get("name", "")
    raw_url = item.get("absolute_url", item.get("url", ""))
    if raw_url and not raw_url.startswith("http"):
        raw_url = f"{BASE_URL}{raw_url}" if raw_url.startswith("/") else raw_url

    thumbnail = item.get("obj_img", "")

    designer = item.get("user_name", "")

    likes = item.get("likes", 0)
    visits = item.get("visits", 0)
    price_obj = item.get("price") or {}
    price_value = price_obj.get("value") if isinstance(price_obj, dict) else None
    currency = price_obj.get("currency", "") if isinstance(price_obj, dict) else ""

    return {
        "title": title,
        "url": raw_url,
        "thumbnail": thumbnail,
        "designer": designer,
        "likes": likes,
        "visits": visits,
        "currency": currency,
        "price": price_value,
        "sku": item.get("sku", ""),
        "category": item.get("category_name", ""),
    }


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []

    for query in SEED_QUERIES:
        limiter.wait()
        result = ScoutResult(source="myminifactory", keyword_or_category=query)
        headers = build_browser_headers()
        headers["Accept"] = "application/json, text/plain, */*"
        try:
            resp = session.get(
                SEARCH_API,
                params={"q": query, "sort": "popular", "per_page": 20},
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    result.errors.append("Invalid JSON response")
                    results.append(result)
                    continue

                raw_items = data.get("objectResults", [])
                for item in raw_items:
                    result.items.append(extract_item(item))

                result.metadata["total_results"] = len(result.items)
                result.metadata["total_objects"] = data.get("totalObjects", 0)
                result.metadata["query"] = query
            else:
                result.errors.append(f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            result.errors.append(str(e))

        results.append(result)

    return results
