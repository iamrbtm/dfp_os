from __future__ import annotations

import logging
import os
from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import ScoutResult, request_with_retry

logger = logging.getLogger(__name__)

BASE_URL = "https://openapi.etsy.com/v3"

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
    application_api_key = os.getenv("ETSY_API_KEY", "")

    if not application_api_key:
        logger.warning(
            "ETSY_API_KEY not configured. Etsy source requires an API key "
            "from https://developers.etsy.com/. Skipping Etsy queries."
        )
        result = ScoutResult(
            source="etsy",
            keyword_or_category="not_configured",
            errors=["ETSY_API_KEY environment variable not set"],
        )
        result.metadata["note"] = "Set ETSY_API_KEY in your environment to enable Etsy trend data"
        results.append(result)
        return results

    headers = {"x-api-key": application_api_key}

    for query in SEED_QUERIES:
        limiter.wait()
        result = ScoutResult(source="etsy", keyword_or_category=query)
        try:
            resp = request_with_retry(
                session, "GET",
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
                    price = None
                    currency = ""
                    if "price" in item and isinstance(item["price"], dict):
                        amount = item["price"].get("amount")
                        divisor = item["price"].get("divisor", 1)
                        if amount is not None:
                            try:
                                divisor_value = float(divisor or 1)
                                price = float(amount) / divisor_value if divisor_value else None
                            except (TypeError, ValueError):
                                price = None
                        currency = item["price"].get("currency_code", "")

                    result.items.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("url", str(item.get("listing_id", ""))),
                            "thumbnail": (
                                item.get("images", [{}])[0].get("url_570xN", "")
                                if item.get("images")
                                else ""
                            ),
                            "price": price,
                            "currency": currency,
                            "tags": item.get("tags", []),
                            "views": item.get("views", 0),
                            "num_favorers": item.get("num_favorers", 0),
                            "category": item.get("taxonomy_path", []),
                            "is_customizable": item.get("is_customizable", False),
                            "shop_name": (
                                item.get("Shop", {}).get("shop_name", "")
                                if isinstance(item.get("Shop"), dict)
                                else ""
                            ),
                        }
                    )
                result.metadata["total_results"] = len(result.items)
                result.metadata["query"] = query
            elif resp.status_code == 401:
                result.errors.append(
                    "HTTP 401 - Invalid or missing Etsy API key. " "Verify ETSY_API_KEY is correct."
                )
            else:
                result.errors.append(f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            result.errors.append(str(e))

        results.append(result)

    return results
