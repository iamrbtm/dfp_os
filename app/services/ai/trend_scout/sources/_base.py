from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

MIN_REQUEST_INTERVAL = 3.0


class RateLimiter:
    def __init__(self, interval: float = MIN_REQUEST_INTERVAL):
        self._interval = interval
        self._last_call: float = 0.0

    def wait(self):
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
