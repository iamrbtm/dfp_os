from __future__ import annotations

import re


def _normalize_key(name: str) -> str:
    """Normalize a name for exact-match dedup (lowercase, alnum/space only)."""
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


_COUNTY_RE = re.compile(r"\b([A-Za-z]+)\s+County\b", re.I)


def extract_county(name: str) -> str | None:
    """Pull the county token from a fair name like 'Clay County Fair'."""
    m = _COUNTY_RE.search(name or "")
    return m.group(1).title() if m else None
