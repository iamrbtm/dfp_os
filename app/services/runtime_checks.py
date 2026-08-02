"""Runtime capability and health probes (Issues 32, 4).

These helpers let the app surface a studio banner when trimesh/PrusaSlicer are
unavailable and when the Celery broker is not reachable, so the UI can warn the
operator before they kick off an analysis run that would silently fail.
"""

from __future__ import annotations

import os
import subprocess


def check_trimesh_available() -> bool:
    """Return ``True`` if ``trimesh`` imports (used for geometry validation)."""
    try:
        import trimesh  # noqa: F401
    except Exception:
        return False
    return True


def check_prusaslicer_available() -> bool:
    """Return ``True`` if the PrusaSlicer binary responds to ``--help-fff``.

    Honours the ``PRUSA_SLICER_PATH`` environment variable; defaults to
    ``prusa-slicer``. The check is bounded to 10 seconds so a hung binary does
    not block the studio banner render.
    """
    prusa_bin = os.environ.get("PRUSA_SLICER_PATH", "prusa-slicer")
    try:
        proc = subprocess.run(
            [prusa_bin, "--help-fff"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return False
    return proc.returncode == 0


def check_slicer_service_available() -> bool:
    """Return ``True`` if the slicer microservice health check passes.

    Uses the SLICER_SERVICE_URL and SLICER_INTERNAL_API_TOKEN config values.
    Falls back to checking the local PrusaSlicer binary if the service is not
    configured (for local development without docker-compose).
    """
    from flask import current_app

    config = current_app.config
    service_url = config.get("SLICER_SERVICE_URL", "")
    token = config.get("SLICER_INTERNAL_API_TOKEN", "")
    enabled = config.get("SLICER_ENABLED", False)

    if not enabled or not service_url or not token:
        return check_prusaslicer_available()

    try:
        import httpx

        with httpx.Client(
            base_url=service_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        ) as client:
            response = client.get("/health/ready")
            if response.status_code == 200:
                data = response.json()
                return data.get("status") == "ready"
    except Exception:
        return False
    return False


def runtime_health() -> dict[str, bool]:
    """Aggregate capability flags for the studio banner (Issue 32)."""
    return {
        "trimesh": check_trimesh_available(),
        "prusaslicer": check_slicer_service_available(),
    }


def is_celery_healthy() -> bool:
    """Ping the Celery broker and return ``True`` if it responds (Issue 4).

    Any error (broker down, misconfigured, import failure) resolves to
    ``False`` so the UI can degrade gracefully.
    """
    try:
        from app.celery_app import celery

        return bool(celery.control.ping(timeout=1))
    except Exception:
        return False


__all__ = [
    "check_trimesh_available",
    "check_prusaslicer_available",
    "check_slicer_service_available",
    "runtime_health",
    "is_celery_healthy",
]
