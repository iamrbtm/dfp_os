from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.services.ai.trend_scout.sources._base import (
    ScoutResult,
    random_user_agent,
)

RSS_FEEDS = {
    "popular": "https://www.printables.com/models.rss?sort=-printCount",
    "recent": "https://www.printables.com/models.rss?sort=-created",
    "makes": "https://www.printables.com/makes.rss",
}

CATEGORY_URLS = [
    "https://www.printables.com/models?sort=-printCount&category=3d-printed-figurines",
    "https://www.printables.com/models?sort=-printCount&category=toys-games",
    "https://www.printables.com/models?sort=-printCount&category=household",
    "https://www.printables.com/models?sort=-printCount&category=organizers",
    "https://www.printables.com/models?sort=-printCount&category=jewelry",
    "https://www.printables.com/models?sort=-printCount&category=cosplay",
    "https://www.printables.com/models?sort=-printCount&category=art",
    "https://www.printables.com/models?sort=-printCount&category=gadgets",
    "https://www.printables.com/models?sort=-printCount&category=board-games",
    "https://www.printables.com/models?sort=-printCount&category=containers",
]


def _parse_rss_item(item_el: Any) -> dict[str, Any]:
    ns = {"rss": "http://purl.org/rss/1.0/", "dc": "http://purl.org/dc/elements/1.1/"}
    title_el = item_el.find("rss:title", ns) or item_el.find("title")
    link_el = item_el.find("rss:link", ns) or item_el.find("link")
    desc_el = item_el.find("rss:description", ns) or item_el.find("description")
    creator_el = item_el.find("dc:creator", ns)

    return {
        "title": title_el.text.strip() if title_el is not None and title_el.text else "",
        "url": link_el.text.strip() if link_el is not None and link_el.text else "",
        "description": desc_el.text.strip()[:500] if desc_el is not None and desc_el.text else "",
        "creator": creator_el.text.strip() if creator_el is not None and creator_el.text else "",
    }


def _parse_model_card(card) -> dict[str, Any]:
    title_el = card.select_one("h3, h4, .model-title, [class*=title] a")
    link_el = card.select_one("a[href]")
    img_el = card.select_one("img[src]")
    print_count_el = card.select_one("[class*=print-count], [class*=makes], [class*=stats]")

    return {
        "title": title_el.get_text(strip=True) if title_el else "",
        "url": f"https://www.printables.com{link_el['href']}" if link_el and link_el.get("href", "").startswith("/") else (link_el["href"] if link_el else ""),
        "thumbnail": img_el.get("src", "") if img_el else "",
        "print_count_text": print_count_el.get_text(strip=True) if print_count_el else "",
    }


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []
    headers = {"User-Agent": random_user_agent()}

    # Parse RSS feeds
    for feed_key, feed_url in RSS_FEEDS.items():
        limiter.wait()
        result = ScoutResult(source="printables", keyword_or_category=feed_key)
        try:
            resp = session.get(feed_url, headers=headers, timeout=30)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                for item_el in root.iter("item"):
                    result.items.append(_parse_rss_item(item_el))
                result.metadata["total_results"] = len(result.items)
                result.metadata["feed"] = feed_key
            else:
                result.errors.append(f"HTTP {resp.status_code}")
        except (requests.RequestException, ET.ParseError) as e:
            result.errors.append(str(e))
        results.append(result)

    # Scrape category pages
    for cat_url in CATEGORY_URLS:
        limiter.wait()
        cat_slug = cat_url.split("category=")[-1]
        cat_result = ScoutResult(source="printables", keyword_or_category=f"category_{cat_slug}")
        try:
            resp = session.get(cat_url, headers=headers, timeout=30)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("[class*=card], [class*=model-card], article, [class*=model-item]")
                for card in cards[:20]:
                    cat_result.items.append(_parse_model_card(card))
                cat_result.metadata["total_results"] = len(cat_result.items)
                cat_result.metadata["category"] = cat_slug
            else:
                cat_result.errors.append(f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            cat_result.errors.append(str(e))
        results.append(cat_result)

    return results
