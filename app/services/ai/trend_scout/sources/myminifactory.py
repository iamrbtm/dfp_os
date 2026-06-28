from __future__ import annotations

from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import ScoutResult

BASE_URL = "https://www.myminifactory.com/api/v2"
SEARCH_ENDPOINT = f"{BASE_URL}/search"

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


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []
    headers = {"User-Agent": "DFPosTrendScout/1.0 (research; admin@dudefishprinting.com)"}

    for query in SEED_QUERIES:
        limiter.wait()
        result = ScoutResult(source="myminifactory", keyword_or_category=query)
        try:
            resp = session.get(
                SEARCH_ENDPOINT,
                params={"q": query, "sort": "popular", "per_page": 20},
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", data.get("items", [])):
                    result.items.append(
                        {
                            "title": item.get("name", item.get("title", "")),
                            "url": item.get("url", item.get("public_url", "")),
                            "thumbnail": item.get("thumbnail", item.get("main_photo", "")),
                            "designer": item.get("designer", {}).get("name", "") if isinstance(item.get("designer"), dict) else "",
                            "likes": item.get("likes_count", item.get("like_count", 0)),
                            "downloads": item.get("downloads_count", item.get("download_count", 0)),
                            "makes_count": item.get("makes_count", 0),
                            "currency": item.get("currency", ""),
                            "price": item.get("price", item.get("price_amount", None)),
                            "tags": item.get("tags", []),
                        }
                    )
                result.metadata["total_results"] = len(result.items)
                result.metadata["query"] = query
            else:
                result.errors.append(f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            result.errors.append(str(e))

        results.append(result)

    return results
