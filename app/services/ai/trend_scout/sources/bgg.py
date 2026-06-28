from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import requests

from app.services.ai.trend_scout.sources._base import ScoutResult

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


def fetch_hot_items(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []
    headers = {"User-Agent": "DFPosTrendScout/1.0"}

    for category in HOT_CATEGORIES:
        limiter.wait()
        result = ScoutResult(source="bgg", keyword_or_category=f"hot_{category}")
        try:
            resp = session.get(HOT_ITEMS_URL, params={"type": category}, headers=headers, timeout=30)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item_el in root.findall("item"):
                    name_el = item_el.find("name")
                    year_el = item_el.find("yearpublished")
                    result.items.append(
                        {
                            "id": item_el.get("id"),
                            "name": name_el.get("value") if name_el is not None else "",
                            "year_published": year_el.get("value") if year_el is not None else None,
                            "rank": int(item_el.get("rank", 0)) if item_el.get("rank") else None,
                            "thumbnail": item_el.get("thumbnail", ""),
                            "type": category,
                        }
                    )
                result.metadata["total_results"] = len(result.items)
                result.metadata["category"] = category
            else:
                result.errors.append(f"HTTP {resp.status_code}")
        except (requests.RequestException, ET.ParseError) as e:
            result.errors.append(str(e))

        results.append(result)

    for query in SEED_QUERIES:
        limiter.wait()
        result = ScoutResult(source="bgg", keyword_or_category=query)
        try:
            resp = session.get(SEARCH_URL, params={"query": query, "type": "boardgameaccessory"}, headers=headers, timeout=30)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item_el in root.findall("item"):
                    name_el = item_el.find("name")
                    year_el = item_el.find("yearpublished")
                    result.items.append(
                        {
                            "id": item_el.get("id"),
                            "name": name_el.get("value") if name_el is not None else "",
                            "year_published": year_el.get("value") if year_el is not None else None,
                            "type": item_el.get("type"),
                        }
                    )
                result.metadata["total_results"] = len(result.items)
                result.metadata["query"] = query
            else:
                result.errors.append(f"HTTP {resp.status_code}")
        except (requests.RequestException, ET.ParseError) as e:
            result.errors.append(str(e))

        results.append(result)

    return results
