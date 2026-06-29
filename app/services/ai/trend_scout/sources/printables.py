from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import requests
from bs4 import BeautifulSoup

from app.services.ai.trend_scout.sources._base import (
    ScoutResult,
    build_browser_headers,
    build_rss_headers,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.printables.com"

RSS_FEED_CANDIDATES = [
    "https://www.printables.com/models.rss",
    "https://www.printables.com/en/models.rss",
    "https://www.printables.com/feed/models.rss",
    "https://www.printables.com/rss/models",
    "https://www.printables.com/feed",
]

SEARCH_QUERIES = [
    "dragon articulated",
    "flexi animal fidget",
    "board game organizer insert",
    "cosplay prop",
    "jewelry earrings",
    "gridfinity",
    "desk organizer",
    "lamp shade",
    "planter pot",
    "keychain custom",
    "miniature terrain",
]


def _parse_model_card(card) -> dict[str, Any]:
    title_el = card.select_one("h5 a, a.h.clamp-two-lines")
    title = title_el.get_text(strip=True) if title_el else ""

    link_el = card.select_one("a[href*='/model/']")
    href = link_el.get("href", "") if link_el else ""
    url = f"{BASE_URL}{href}" if href.startswith("/") else href

    img_el = card.select_one("a.card-image img, img[alt]")
    thumbnail = ""
    alt_text = ""
    if img_el:
        src = img_el.get("src", "")
        if src and not src.startswith("data:"):
            thumbnail = src
        alt_text = img_el.get("alt", "")

    creator_el = card.select_one("span.username, a.username .username, .name-and-handle .username")
    creator = creator_el.get_text(strip=True) if creator_el else ""

    like_el = card.select_one("[data-testid='like-count'], .stats-bar .big-icon span")
    likes_text = like_el.get_text(strip=True) if like_el else ""

    rating_el = card.select_one(".hide-when-small-card .small-icon span + span, .stats-bar .small-icon:nth-child(2) span")
    rating = rating_el.get_text(strip=True) if rating_el else ""

    download_spans = card.select(".stats-bar .small-icon span")
    downloads = ""
    if len(download_spans) >= 2:
        downloads = download_spans[1].get_text(strip=True)

    return {
        "title": title or alt_text,
        "url": url,
        "thumbnail": thumbnail,
        "creator": creator,
        "likes": likes_text,
        "rating": rating,
        "downloads": downloads,
    }


def _search_models(
    session: requests.Session,
    query: str,
    limiter: Any,
    max_items: int = 15,
) -> ScoutResult:
    result = ScoutResult(source="printables", keyword_or_category=query)
    limiter.wait()
    headers = build_browser_headers()

    try:
        resp = session.get(
            f"{BASE_URL}/search/models",
            params={"q": query, "sort": "-printCount"},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("article.card, article[data-testid='model'], [class*='card'].svelte")
            for card in cards[:max_items]:
                result.items.append(_parse_model_card(card))
            result.metadata["total_results"] = len(result.items)
            result.metadata["query"] = query
        else:
            result.errors.append(f"HTTP {resp.status_code}")
    except requests.RequestException as e:
        result.errors.append(str(e))

    return result


def _try_rss_feeds(
    session: requests.Session,
    limiter: Any,
) -> ScoutResult | None:
    for feed_url in RSS_FEED_CANDIDATES:
        limiter.wait()
        headers = build_rss_headers()
        try:
            resp = session.get(feed_url, headers=headers, timeout=30)
            if resp.status_code == 200:
                try:
                    root = ET.fromstring(resp.text)
                    items = []
                    for item_el in root.iter("item"):
                        item = _parse_rss_item(item_el)
                        if item.get("title"):
                            items.append(item)
                    if items:
                        result = ScoutResult(source="printables", keyword_or_category="rss")
                        result.items = items
                        result.metadata["total_results"] = len(items)
                        result.metadata["feed_url"] = feed_url
                        logger.info("RSS feed working: %s (%d items)", feed_url, len(items))
                        return result
                except ET.ParseError:
                    continue
        except (requests.RequestException, ET.ParseError):
            continue
    return None


def _parse_rss_item(item_el: Any) -> dict[str, Any]:
    ns = {
        "rss": "http://purl.org/rss/1.0/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "atom": "http://www.w3.org/2005/Atom",
    }
    title_el = (
        item_el.find("rss:title", ns)
        or item_el.find("title")
        or item_el.find("atom:title", ns)
    )
    link_el = (
        item_el.find("rss:link", ns)
        or item_el.find("link")
        or item_el.find("atom:link", ns)
    )
    desc_el = (
        item_el.find("rss:description", ns)
        or item_el.find("description")
        or item_el.find("atom:content", ns)
    )
    creator_el = item_el.find("dc:creator", ns)

    title = ""
    if title_el is not None:
        title = title_el.text.strip() if title_el.text else title_el.get("value", "")

    link = ""
    if link_el is not None:
        link = link_el.text.strip() if link_el.text else link_el.get("href", "")

    description = ""
    if desc_el is not None:
        text = desc_el.text.strip() if desc_el.text else ""
        if text:
            text = BeautifulSoup(text, "html.parser").get_text(strip=True)
        description = text[:500]

    creator = ""
    if creator_el is not None and creator_el.text:
        creator = creator_el.text.strip()

    return {
        "title": title,
        "url": link,
        "description": description,
        "creator": creator,
    }


def fetch_trending(session: requests.Session, limiter: Any) -> list[ScoutResult]:
    results: list[ScoutResult] = []

    rss_result = _try_rss_feeds(session, limiter)
    if rss_result:
        results.append(rss_result)

    for query in SEARCH_QUERIES:
        result = _search_models(session, query, limiter)
        results.append(result)

    return results
