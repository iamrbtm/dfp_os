from __future__ import annotations

from celery import Celery
from kombu import Exchange, Queue

from app.config import settings

celery = Celery(
    "dfp_trend_scout",
    include=[
        "app.workers.tasks",
    ],
)

_default_exchange = Exchange("celery", type="direct", durable=True)
_high_priority_queue = Queue(
    "trend_scout",
    exchange=_default_exchange,
    routing_key="trend_scout",
    queue_arguments={"x-max-priority": settings.celery_max_priority},
    durable=True,
)


celery.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_transport_options={
        "priority_steps": list(range(settings.celery_max_priority + 1)),
        "queue_order_strategy": "priority",
    },
    task_queue_max_priority=settings.celery_max_priority,
    task_default_priority=settings.celery_default_priority,
    task_queues=(_high_priority_queue,),
    task_routes={
        "app.workers.tasks.*": {
            "queue": settings.celery_queue,
            "priority": settings.celery_task_priority,
        },
    },
)
