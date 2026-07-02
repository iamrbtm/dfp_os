from __future__ import annotations

import logging
import os
from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import ScoutResult, request_with_retry

logger = logging.getLogger(__name__)

API_BASE = "https://api.pinterest.com/v5"

SEED_QUERIES = [
    "3D printed dragon",
    "3D printed fidget toy",
    "articulated animal 3D print",
    "flexi animal 3D print",
    "3D printed keychain",
    "board game organizer 3D print",
    "3D printed earrings",
    "3D printed planter",
    "tabletop miniature 3D print",
    "3D printed cosplay prop",
    "3D printed desk organizer",
    "3D printed lamp shade",
    "3D printed business card holder",
    "3D printed ornament",
    "3D printed vase",
]


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []
    pinterest_api_key = os.getenv("PINTEREST_API_KEY", "")

    if not pinterest_api_key:
        results.append(
            ScoutResult(
                source="pinterest",
                keyword_or_category="not_configured",
                errors=[
                    "PINTEREST_API_KEY environment variable not set. "
                    "Get a key at https://developers.pinterest.com/"
                ],
            )
        )
        return results

    headers = {"Authorization": f"Bearer {pinterest_api_key}"}

    for query in SEED_QUERIES:
        limiter.wait()
        result = ScoutResult(source="pinterest", keyword_or_category=query)
        try:
            resp = request_with_retry(
                session, "GET",
                f"{API_BASE}/search/pins",
                params={"query": query, "page_size": 20},
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                for pin in data.get("items", []):
                    media = pin.get("media", {}) or {}
                    images = media.get("images", {}) or {}
                    thumbnail = ""
                    for size_key in ["600x600", "400x300", "150x150"]:
                        img = images.get(size_key, {}) or {}
                        if img.get("url"):
                            thumbnail = img["url"]
                            break

                    board_owner = pin.get("board_owner", {}) or {}
                    metrics = pin.get("pin_metrics", {}) or {}

                    result.items.append(
                        {
                            "id": pin.get("id", ""),
                            "title": pin.get("title", ""),
                            "description": pin.get("description", ""),
                            "url": pin.get("link", ""),
                            "thumbnail": thumbnail,
                            "creator": board_owner.get("username", ""),
                            "impressions": metrics.get("impressions", 0),
                            "saves": metrics.get("saves", 0),
                            "domain": pin.get("domain", ""),
                        }
                    )

                result.metadata["total_results"] = len(result.items)
                result.metadata["query"] = query
            elif resp.status_code == 401:
                result.errors.append(
                    "HTTP 401 - Invalid Pinterest API key. " "Verify PINTEREST_API_KEY is correct."
                )
            elif resp.status_code == 403:
                result.errors.append(
                    "HTTP 403 - Pinterest API access denied. "
                    "Your app may not have the required scopes."
                )
            else:
                result.errors.append(f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            result.errors.append(str(e))

        results.append(result)

    return results
