"""Celery workers and tasks for the Trend Scout microservice.

Phase 1 only registers the worker module with Celery so the include path
resolves. Phase 4 (Celery + Redis Streams) will populate this package with
the real stream worker, source fetcher pool, and Celery task definitions.
"""

from __future__ import annotations

from app.celery_app import celery  # noqa: E402,F401  re-export for Celery autodiscovery
