from __future__ import annotations

from celery import Celery as _Celery
from flask import Flask

from celery.schedules import crontab

celery = _Celery(
    "dfp_os",
    include=[
        "app.tasks.model_analysis",
        "app.tasks.cost_calculation",
        "app.tasks.trend_scout",
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
            beat_schedule={
                "trend-scout-monday-6am": {
                    "task": "app.tasks.trend_scout.trend_scout_pipeline",
                    "schedule": crontab(hour=6, minute=0, day_of_week=1),
                    "options": {"soft_time_limit": 900, "time_limit": 960},
                },
            },
        )

    return celery
