"""Celery tasks for the Trend Scout microservice.

Phase 1 only registers the module with Celery so the include path resolves.
Phase 4 (Celery + Redis Streams) will populate this module with the real
pipeline and calibration tasks.
"""

from __future__ import annotations

from app.celery_app import celery  # noqa: F401  re-export for Celery autodiscovery
