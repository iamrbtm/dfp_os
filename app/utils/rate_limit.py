from __future__ import annotations

from collections import defaultdict, deque
from functools import wraps
from time import monotonic
from typing import Callable

from flask import current_app, jsonify, request

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


def rate_limit(
    prefix: str, *, limit: int, window_seconds: int, identifier: str | None = None
) -> Callable:
    """Decorator that throttles a view to ``limit`` calls per ``window_seconds``.

    Issue 52 — product-mutation endpoints get per-endpoint limits. Returns 429
    with a Retry-After header and a friendly JSON message when exceeded. The
    limiter is a no-op when ``RATE_LIMIT_ENABLED`` is false (tests/dev).
    """

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            key = client_key(prefix, identifier)
            if is_limited(key, limit=limit, window_seconds=window_seconds):
                response = jsonify(
                    {
                        "success": False,
                        "error": "Too many requests. Please wait a moment and try again.",
                    }
                )
                response.status_code = 429
                response.headers["Retry-After"] = str(window_seconds)
                return response
            return view(*args, **kwargs)

        return wrapper

    return decorator


def reset_limits() -> None:
    _attempts.clear()
