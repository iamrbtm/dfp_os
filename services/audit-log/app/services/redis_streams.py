"""Redis Streams integration for optional async audit event ingestion.

When AUDIT_USE_REDIS_STREAM=true, events are published to Redis Stream
instead of being written directly to PostgreSQL. A background worker
consumes from the stream and writes to the database.
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from app.config import settings


async def get_redis_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def publish_to_stream(event_data: dict[str, Any]) -> str:
    client = await get_redis_client()
    try:
        message_id = await client.xadd(settings.stream_name, event_data, maxlen=10000)
        return message_id
    finally:
        await client.aclose()


async def check_redis_connected() -> bool:
    try:
        client = await get_redis_client()
        result = await client.ping()
        await client.aclose()
        return result
    except Exception:
        return False
