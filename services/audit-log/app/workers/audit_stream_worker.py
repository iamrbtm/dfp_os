"""Redis Stream consumer worker for the audit log service.

Consumes audit events from Redis Stream and writes them to PostgreSQL.
Run as a separate process when AUDIT_USE_REDIS_STREAM=true.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis

from app.config import settings
from app.services.audit_writer import create_audit_event

logger = logging.getLogger(settings.service_name)

DEAD_LETTER_STREAM = f"{settings.stream_name}.dead"
MAX_RETRIES = 3


async def process_message(data: dict[str, Any]) -> bool:
    try:
        occurred_at = data.get("occurred_at")
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)

        await create_audit_event(
            idempotency_key=data.get("idempotency_key"),
            tenant_id=data.get("tenant_id"),
            occurred_at=occurred_at,
            actor_id=data.get("actor_id"),
            actor_type=data.get("actor_type"),
            actor_display_name=data.get("actor_display_name"),
            action=data.get("action", ""),
            entity_type=data.get("entity_type", ""),
            entity_id=data.get("entity_id"),
            source_service=data.get("source_service", ""),
            source_module=data.get("source_module"),
            request_id=data.get("request_id"),
            correlation_id=data.get("correlation_id"),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
            before_state=data.get("before_state"),
            after_state=data.get("after_state"),
            metadata=data.get("metadata"),
        )
        return True
    except Exception as exc:
        logger.error("Failed to process audit event: %s", exc)
        return False


async def run_worker() -> None:
    logger.info("Starting audit stream worker (consumer group: %s)", settings.stream_consumer_group)
    client = aioredis.from_url(settings.redis_url, decode_responses=True)

    try:
        await client.xgroup_create(settings.stream_name, settings.stream_consumer_group, id="0", mkstream=True)
    except Exception:
        pass

    while True:
        try:
            results = await client.xreadgroup(
                groupname=settings.stream_consumer_group,
                consumername=settings.stream_consumer_name,
                streams={settings.stream_name: ">"},
                count=10,
                block=5000,
            )

            if not results:
                await asyncio.sleep(0.1)
                continue

            for stream_name, messages in results:
                for msg_id, msg_data in messages:
                    retry_count = 0
                    success = await process_message(msg_data)
                    if success:
                        await client.xack(settings.stream_name, settings.stream_consumer_group, msg_id)
                    else:
                        retry_count += 1
                        if retry_count >= MAX_RETRIES:
                            await client.xadd(
                                DEAD_LETTER_STREAM,
                                {"original_message": json.dumps(msg_data), "original_id": msg_id},
                            )
                            await client.xack(settings.stream_name, settings.stream_consumer_group, msg_id)
                            logger.warning(
                                "Moved message %s to dead-letter stream after %d retries",
                                msg_id,
                                MAX_RETRIES,
                            )
        except Exception as exc:
            logger.error("Worker error: %s", exc)
            await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=settings.log_level)
    asyncio.run(run_worker())
