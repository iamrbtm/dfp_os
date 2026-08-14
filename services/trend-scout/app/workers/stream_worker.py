"""Redis Streams consumer for the Trend Scout microservice.

Drains ``trend:run:requests`` (Phase 4 default stream) when ``enable_redis_streams``
is True. The pipeline runner writes to this stream; the worker drains it and
runs the pipeline, providing:
- Buffering when the DB is briefly unavailable
- Multi-replica fan-out via Redis consumer groups
- Replay on worker restart via XAUTOCLAIM

Phase 4 wires the stream but does not move the fetchers onto it (they still
run inside the Celery task). Phase 10 will move heavy fetches onto streams
once we have observed the cost / benefit in production.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.services.pipeline_runner import run_full_pipeline

logger = logging.getLogger(__name__)


STREAM_RUN_REQUESTS = "trend:run:requests"


async def _enqueue_run_request(
    run_id: str,
    trigger: str,
    business_id: int | None = None,
    redis_client: Any | None = None,
) -> str:
    """Add a run request to the Redis stream. Returns the entry id."""
    import redis.asyncio as redis_async

    client = redis_client or redis_async.from_url(settings.redis_url, decode_responses=True)
    try:
        payload = {
            "run_id": run_id,
            "trigger": trigger,
            "business_id": business_id or 0,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        }
        entry_id = await client.xadd(STREAM_RUN_REQUESTS, payload)
        return entry_id
    finally:
        if redis_client is None:
            await client.aclose()


async def _drain_one(
    redis_client: Any,
    consumer_name: str,
    block_ms: int,
) -> bool:
    """Drain a single entry from the stream, run the pipeline, acknowledge.

    Returns True if an entry was processed, False if the stream is empty.
    """
    streams = await redis_client.xreadgroup(
        groupname=settings.stream_consumer_group,
        consumername=consumer_name,
        streams={STREAM_RUN_REQUESTS: ">"},
        count=1,
        block=block_ms,
    )
    if not streams:
        return False

    stream_entries = streams[0][1]
    if not stream_entries:
        return False

    entry_id, fields = stream_entries[0]
    payload = {k: v for k, v in fields.items()}
    try:
        run_id = payload.get("run_id") or f"stream-{entry_id}"
        trigger = payload.get("trigger") or "stream"

        async def _factory() -> AsyncSession:
            return async_session_factory()

        await run_full_pipeline(
            session_factory=_factory,
            run_id=run_id,
            trigger=trigger,
        )
    except Exception:
        logger.exception("Stream worker failed on entry %s", entry_id)
    finally:
        await redis_client.xack(
            STREAM_RUN_REQUESTS,
            settings.stream_consumer_group,
            entry_id,
        )
    return True


async def run_worker(consumer_name: str, max_iterations: int | None = None) -> int:
    """Run the worker loop. Returns the number of entries processed."""
    if not settings.enable_redis_streams:
        logger.info("Redis streams disabled; worker is a no-op")
        return 0

    import redis.asyncio as redis_async

    client = redis_async.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.xgroup_create(
            STREAM_RUN_REQUESTS,
            settings.stream_consumer_group,
            mkstream=True,
        )
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            logger.warning("xgroup_create failed: %s", exc)

    processed = 0
    try:
        while max_iterations is None or processed < max_iterations:
            drained = await _drain_one(client, consumer_name, settings.stream_block_ms)
            if not drained:
                break
            processed += 1
    finally:
        await client.aclose()
    return processed
