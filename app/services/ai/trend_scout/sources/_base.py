from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
]

MIN_REQUEST_INTERVAL = 3.0


def build_browser_headers() -> dict[str, str]:
    ua = random_user_agent()
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-GPC": "1",
    }


def build_json_api_headers() -> dict[str, str]:
    ua = random_user_agent()
    return {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Sec-GPC": "1",
        "Referer": "https://makerworld.com/",
    }


def build_rss_headers() -> dict[str, str]:
    ua = random_user_agent()
    return {
        "User-Agent": ua,
        "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "DNT": "1",
    }


def build_xml_headers() -> dict[str, str]:
    ua = random_user_agent()
    return {
        "User-Agent": ua,
        "Accept": "application/xml, text/xml, */*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    }


class RateLimiter:
    def __init__(self, interval: float = MIN_REQUEST_INTERVAL):
        self._interval = interval
        self._last_call: float = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self._interval:
                time.sleep(self._interval - elapsed)
            self._last_call = time.monotonic()


def random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScoutResult:
    source: str
    keyword_or_category: str
    scraped_at: str = field(default_factory=utc_iso)
    items: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "keyword_or_category": self.keyword_or_category,
            "scraped_at": self.scraped_at,
            "items": self.items,
            "errors": self.errors,
            "metadata": self.metadata,
        }
