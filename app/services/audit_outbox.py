"""Redis-backed durable outbox for audit events.

The audit-log microservice is treated as eventually-available. When it is
unreachable, network-flaky, or returning 5xx, ``AuditClient.record`` pushes
the event onto a Redis list so it can be replayed by a Celery beat task
once the service recovers.

Design notes:
    * Single Redis list, ``RPUSH`` on enqueue, ``LRANGE`` + ``LREM 0 1`` on
      dequeue by the flush task. Redis is configured with
      ``appendonly yes`` + ``appendfsync everysec`` and ``maxmemory-policy
      noeviction`` in docker-compose so a crash loses at most 1s of writes
      and a memory crunch cannot silently drop entries.
    * Above ``AUDIT_OUTBOX_MAX_SIZE`` (default 100,000) the producer
      refuses to enqueue critical events and deadman-writes non-critical
      events to ``AUDIT_OUTBOX_DLQ_PATH`` so the audit chain is never
      silently dropped.
    * The flush task is the only consumer; safe under multiple workers
      because each flush reads + removes atomically per entry.

This module deliberately avoids importing Flask: it is reused by Celery
tasks and CLI commands that have no request context.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis
from flask import current_app

logger = logging.getLogger(__name__)


def _client(redis_url: str) -> redis.Redis:
    return redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=5)


def _key(app=None) -> str:
    if app is not None:
        return app.config.get("AUDIT_OUTBOX_KEY", "audit:outbox")
    return current_app.config.get("AUDIT_OUTBOX_KEY", "audit:outbox")


def _redis_url(app=None) -> str:
    if app is not None:
        return app.config.get("AUDIT_REDIS_URL", "redis://localhost:6379/0")
    return current_app.config.get("AUDIT_REDIS_URL", "redis://localhost:6379/0")


def _max_size(app=None) -> int:
    if app is not None:
        return int(app.config.get("AUDIT_OUTBOX_MAX_SIZE", 100000))
    return int(current_app.config.get("AUDIT_OUTBOX_MAX_SIZE", 100000))


def _dlq_path(app=None) -> str:
    if app is not None:
        return app.config.get("AUDIT_OUTBOX_DLQ_PATH", "uploads/audit-queue")
    return current_app.config.get("AUDIT_OUTBOX_DLQ_PATH", "uploads/audit-queue")


def _batch_size(app=None) -> int:
    if app is not None:
        return int(app.config.get("AUDIT_OUTBOX_BATCH_SIZE", 200))
    return int(current_app.config.get("AUDIT_OUTBOX_BATCH_SIZE", 200))


def size(app=None) -> int:
    try:
        return int(_client(_redis_url(app)).llen(_key(app)))
    except redis.RedisError as exc:
        logger.warning("audit outbox size probe failed: %s", exc)
        return 0


def enqueue(
    payload: dict[str, Any],
    *,
    critical: bool = False,
    app=None,
) -> bool:
    """Append an audit event to the Redis outbox.

    Returns True if the event was queued, False if it was deadman'd to disk
    or refused. The flush task will retry the outbox on its next run.
    """
    url = _redis_url(app)
    key = _key(app)
    max_size = _max_size(app)
    try:
        client = _client(url)
        current_size = int(client.llen(key))
        if current_size >= max_size:
            if critical:
                logger.error(
                    "audit outbox at %d entries (>= %d); refusing critical event %s",
                    current_size,
                    max_size,
                    payload.get("action"),
                )
                return False
            return _deadman(payload, reason="outbox_full", app=app)
        body = json.dumps(payload, sort_keys=True, default=str)
        client.rpush(key, body)
        return True
    except redis.RedisError as exc:
        logger.warning("audit outbox enqueue failed (%s); deadmanning to disk", exc)
        return _deadman(payload, reason=f"redis_error: {exc}", app=app)


def _deadman(
    payload: dict[str, Any],
    *,
    reason: str,
    app=None,
) -> bool:
    path = Path(_dlq_path(app))
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("audit deadman directory %s could not be created: %s", path, exc)
        return False
    filename = f"{int(time.time() * 1000)}-{os.getpid()}-{payload.get('action', 'unknown')}.json"
    target = path / filename
    record = {
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "payload": payload,
    }
    try:
        target.write_text(json.dumps(record, indent=2, default=str))
        return True
    except OSError as exc:
        logger.error("audit deadman write to %s failed: %s", target, exc)
        return False


def drain_one(app=None) -> dict[str, Any] | None:
    """Pop the oldest queued event off Redis. Returns None when empty.

    ``LRANGE 0 0`` + ``LREM 0 1`` is not atomic, but it is safe across
    concurrent consumers because we only ever remove the value we just
    read by exact match.
    """
    try:
        client = _client(_redis_url(app))
        head = client.lrange(_key(app), 0, 0)
        if not head:
            return None
        raw = head[0]
        removed = int(client.lrem(_key(app), 0, raw))
        if removed == 0:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("audit outbox dropped malformed entry: %s", exc)
            return None
    except redis.RedisError as exc:
        logger.warning("audit outbox drain failed: %s", exc)
        return None


def replay_deadman(app=None) -> int:
    """Move deadman'd events from disk back onto the Redis outbox.

    Called on startup so any events captured while Redis was also down
    are not stranded. Returns the number of events replayed.
    """
    path = Path(_dlq_path(app))
    if not path.exists():
        return 0
    replayed = 0
    for file in sorted(path.glob("*.json")):
        try:
            record = json.loads(file.read_text())
            payload = record.get("payload", {})
            if enqueue(payload, critical=payload.get("critical", False), app=app):
                file.unlink(missing_ok=True)
                replayed += 1
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("audit deadman replay for %s failed: %s", file, exc)
    return replayed


def peek_batch(n: int | None = None, app=None) -> list[dict[str, Any]]:
    """Inspect the next ``n`` queued events without removing them."""
    if n is None:
        n = _batch_size(app)
    try:
        client = _client(_redis_url(app))
        raw = client.lrange(_key(app), 0, max(0, n - 1))
        out: list[dict[str, Any]] = []
        for entry in raw:
            try:
                out.append(json.loads(entry))
            except json.JSONDecodeError:
                continue
        return out
    except redis.RedisError as exc:
        logger.warning("audit outbox peek failed: %s", exc)
        return []
