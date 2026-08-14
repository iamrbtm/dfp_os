"""Task run monitor for the Trend Scout microservice.

Mirrors ``app/services/trend_scout_task_monitor.py`` from the monolith so the
admin UI proxy in Phase 6 can render the same fields. Phase 4 in-memory
implementation; Phase 10 may add Redis-backed storage for cross-process
visibility.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_task_runs: dict[str, dict[str, Any]] = {}


def create_task_run(
    task_id: str,
    trigger: str,
    total_steps: int,
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    with _lock:
        _task_runs[task_id] = {
            "task_id": task_id,
            "run_id": run_id,
            "trigger": trigger,
            "total_steps": total_steps,
            "current_step": "created",
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "metadata": metadata or {},
        }


def start_task_run(task_id: str) -> None:
    with _lock:
        run = _task_runs.get(task_id)
        if not run:
            return
        run["status"] = "running"
        run["started_at"] = datetime.now(timezone.utc).isoformat()


def update_task_progress(
    task_id: str,
    completed_steps: int | None = None,
    total_steps: int | None = None,
    current_step: str | None = None,
    status: str | None = None,
) -> None:
    with _lock:
        run = _task_runs.get(task_id)
        if not run:
            return
        if completed_steps is not None:
            run["completed_steps"] = completed_steps
        if total_steps is not None:
            run["total_steps"] = total_steps
        if current_step is not None:
            run["current_step"] = current_step
        if status is not None:
            run["status"] = status


def complete_task_run(
    task_id: str,
    status: str = "success",
    error: str | None = None,
) -> None:
    with _lock:
        run = _task_runs.get(task_id)
        if not run:
            return
        run["status"] = status
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        run["error"] = error


def get_task_run(task_id: str) -> dict[str, Any] | None:
    with _lock:
        if task_id in _task_runs:
            return dict(_task_runs[task_id])
        return None


def list_task_runs(limit: int = 25) -> list[dict[str, Any]]:
    with _lock:
        runs = sorted(
            _task_runs.values(),
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )
        return [dict(r) for r in runs[:limit]]
