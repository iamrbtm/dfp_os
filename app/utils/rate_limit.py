from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from flask import current_app, request

_attempts: dict[str, deque[float]] = defaultdict(deque)


def client_key(prefix: str, identifier: str | None = None) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    remote_addr = forwarded_for or request.remote_addr or "unknown"
    suffix = (identifier or "").strip().lower()
    return f"{prefix}:{remote_addr}:{suffix}"


def is_limited(key: str, *, limit: int, window_seconds: int) -> bool:
    if not current_app.config.get("RATE_LIMIT_ENABLED", True):
        return False
    now = monotonic()
    bucket = _attempts[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    bucket.append(now)
    return len(bucket) > limit


def reset_limits() -> None:
    _attempts.clear()
