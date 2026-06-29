from __future__ import annotations

import re


def slugify(text: str, max_length: int = 0) -> str:
    """Convert text to a URL-friendly slug.

    Lowercases, replaces whitespace with hyphens, strips special characters,
    collapses multiple hyphens, and strips leading/trailing hyphens.
    """
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    s = s.strip("-")
    if max_length and len(s) > max_length:
        s = s[:max_length].rstrip("-")
    return s
