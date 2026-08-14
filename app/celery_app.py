from __future__ import annotations

import logging

from celery import Celery as _Celery
from celery.signals import worker_ready
from flask import Flask

from celery.schedules import crontab
from kombu import Exchange, Queue

logger = logging.getLogger(__name__)


_DEFAULT_HIGH_PRIORITY = 9
_DEFAULT_LOW_PRIORITY = 1


celery = _Celery(
    "dfp_os",
    include=[
        "app.tasks.model_analysis",
        "app.tasks.cost_calculation",
        "app.tasks.audit_outbox",
        "app.tasks.dispatch_trend_scout",
    ],
)


_flask_app: Flask | None = None


def _get_flask_app() -> Flask:
    global _flask_app
    if _flask_app is None:
        from app import create_app

        _flask_app = create_app()
    return _flask_app


class FlaskTask(celery.Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        with _get_flask_app().app_context():
            return self.run(*args, **kwargs)


celery.Task = FlaskTask


def make_celery(app: Flask | None = None) -> _Celery:
    if app is not None:
        celery.conf.update(
            broker_url=app.config["CELERY_BROKER_URL"],
            result_backend=app.config["CELERY_RESULT_BACKEND"],
            task_serializer="json",
            result_serializer="json",
            accept_content=["json"],
            task_track_started=True,
            task_acks_late=True,
            worker_prefetch_multiplier=1,
            result_expires=3600,
            broker_transport_options={
                "priority_steps": list(range(11)),
                "queue_order_strategy": "priority",
            },
            task_queue_max_priority=10,
            task_default_priority=_DEFAULT_HIGH_PRIORITY,
            task_queues=(
                Queue(
                    "celery",
                    Exchange("celery", type="direct", durable=True),
                    routing_key="celery",
                    queue_arguments={"x-max-priority": 10},
                    durable=True,
                ),
                Queue(
                    "trend_scout",
                    Exchange("celery", type="direct", durable=True),
                    routing_key="trend_scout",
                    queue_arguments={"x-max-priority": 10},
                    durable=True,
                ),
            ),
            task_routes={
                "app.tasks.dispatch_trend_scout.*": {
                    "queue": "trend_scout",
                    "priority": _DEFAULT_LOW_PRIORITY,
                },
            },
            beat_schedule={
                "trend-scout-monday-6am": {
                    "task": "app.tasks.dispatch_trend_scout.dispatch_trend_scout_run",
                    "schedule": crontab(hour=6, minute=0, day_of_week=1),
                    "options": {"queue": "trend_scout", "priority": _DEFAULT_LOW_PRIORITY},
                },
                "trend-scout-calibration-1st-of-month": {
                    "task": "app.tasks.dispatch_trend_scout.dispatch_trend_scout_calibration",
                    "schedule": crontab(hour=5, minute=0, day_of_month=1),
                    "options": {"queue": "trend_scout", "priority": _DEFAULT_LOW_PRIORITY},
                },
                "audit-outbox-flush": {
                    "task": "app.tasks.audit_outbox.flush_outbox",
                    "schedule": float(app.config.get("AUDIT_OUTBOX_FLUSH_INTERVAL_SECONDS", 30)),
                    "options": {"queue": "celery"},
                },
                "audit-deadman-replay": {
                    "task": "app.tasks.audit_outbox.replay_deadman",
                    "schedule": float(app.config.get("AUDIT_OUTBOX_REPLAY_INTERVAL_SECONDS", 60)),
                    "options": {"queue": "celery"},
                },
            },
        )

    return celery


@worker_ready.connect
def _replay_audit_deadman_on_worker_ready(sender=None, **kwargs) -> None:
    """Move any deadman'd audit events back onto the Redis outbox as
    soon as the worker is ready to receive tasks.

    The web container also calls ``replay_deadman`` at startup, but
    if the worker comes up first (e.g. a deploy only restarts the
    worker) the deadman files would otherwise sit idle until the next
    web restart. Doing this in the worker means a single container
    restart is enough to recover after an outage.
    """
    try:
        from app.tasks.audit_outbox import replay_deadman_task

        replay_deadman_task.apply_async(countdown=2)
        logger.info("scheduled audit deadman replay on worker_ready")
    except Exception as exc:
        logger.warning("could not schedule audit deadman replay: %s", exc)
