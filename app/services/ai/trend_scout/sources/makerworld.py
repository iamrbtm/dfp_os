from __future__ import annotations

from typing import Any

import requests
from bs4 import BeautifulSoup

from app.services.ai.trend_scout.sources._base import (
    ScoutResult,
    random_user_agent,
)

BASE_URL = "https://makerworld.com"
POPULAR_URL = f"{BASE_URL}/en/popular"
CATEGORIES_URL = f"{BASE_URL}/en/models"

CATEGORY_PATHS = [
    "/en/models?category=art",
    "/en/models?category=lifestyle",
    "/en/models?category=organizer",
    "/en/models?category=toy",
    "/en/models?category=gadget",
    "/en/models?category=cosplay",
    "/en/models?category=miniature",
    "/en/models?category=board-game",
    "/en/models?category=fidget",
    "/en/models?category=animals",
]


def _parse_card(card) -> dict[str, Any]:
    title_el = card.select_one("h3, h4, .title, [class*=title]")
    link_el = card.select_one("a[href]")
    img_el = card.select_one("img[src]")
    meta_el = card.select_one("[class*=like], [class*=download], [class*=print]")

    return {
        "title": title_el.get_text(strip=True) if title_el else "",
        "url": f"{BASE_URL}{link_el['href']}" if link_el and link_el.get("href", "").startswith("/") else (link_el["href"] if link_el else ""),
        "thumbnail": img_el.get("src", "") if img_el else "",
        "raw_text": meta_el.get_text(strip=True) if meta_el else "",
    }


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []

    # Fetch popular page
    limiter.wait()
    result = ScoutResult(source="makerworld", keyword_or_category="popular")
    headers = {"User-Agent": random_user_agent()}
    try:
        resp = session.get(POPULAR_URL, headers=headers, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("[class*=card], [class*=item], [class*=model-card]")
            for card in cards[:40]:
                result.items.append(_parse_card(card))
            result.metadata["total_results"] = len(result.items)
            result.metadata["source"] = "popular"
        else:
            result.errors.append(f"HTTP {resp.status_code}")
    except requests.RequestException as e:
        result.errors.append(str(e))
    results.append(result)

    # Fetch category pages
    for cat_path in CATEGORY_PATHS:
        limiter.wait()
        slug = cat_path.split("category=")[-1]
        cat_result = ScoutResult(source="makerworld", keyword_or_category=f"category_{slug}")
        try:
            resp = session.get(f"{BASE_URL}{cat_path}", headers=headers, timeout=30)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("[class*=card], [class*=item], [class*=model-card]")
                for card in cards[:20]:
                    cat_result.items.append(_parse_card(card))
                cat_result.metadata["total_results"] = len(cat_result.items)
                cat_result.metadata["category"] = slug
            else:
                cat_result.errors.append(f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            cat_result.errors.append(str(e))
        results.append(cat_result)

    return results
