from __future__ import annotations

import os
from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import ScoutResult

BASE_URL = "https://openapi.etsy.com/v3"
APPLICATION_API_KEY = os.getenv("ETSY_API_KEY", "")

SEED_QUERIES = [
    "3D printed dragon",
    "3D printed fidget",
    "3D printed articulated animal",
    "3D printed earrings",
    "custom keychain",
    "3D printed planter",
    "3D printed lamp",
    "3D printed vase",
    "3D printed cosplay",
    "3D printed miniature",
    "3D printed game piece",
    "3D printed jewelry",
    "3D printed ornament",
    "3D printed desk accessory",
    "3D printed business card holder",
    "acrylic sign holder",
    "tabletop organizer",
]


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []
    headers = {"x-api-key": APPLICATION_API_KEY} if APPLICATION_API_KEY else {}

    for query in SEED_QUERIES:
        limiter.wait()
        result = ScoutResult(source="etsy", keyword_or_category=query)
        try:
            resp = session.get(
                f"{BASE_URL}/application/listings/active",
                params={
                    "keywords": query,
                    "limit": 20,
                    "sort_on": "score",
                    "sort_order": "desc",
                },
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("results", []):
                    result.items.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("url", item.get("listing_id", "")),
                            "thumbnail": (
                                item.get("images", [{}])[0].get("url_570xN", "")
                                if item.get("images")
                                else ""
                            ),
                            "price": float(item["price"]["amount"]) / (10 ** item["price"]["divisor"]) if "price" in item else None,
                            "currency": item.get("price", {}).get("currency_code", ""),
                            "tags": item.get("tags", []),
                            "views": item.get("views", 0),
                            "num_favorers": item.get("num_favorers", 0),
                            "category": item.get("taxonomy_path", []),
                            "is_customizable": item.get("is_customizable", False),
                            "shop_name": item.get("Shop", {}).get("shop_name", "") if isinstance(item.get("Shop"), dict) else "",
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
