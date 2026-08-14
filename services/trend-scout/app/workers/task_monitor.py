"""Task run monitor for the Trend Scout microservice.

Redis is the production store so the API and Celery worker containers share
run progress. A small in-memory fallback keeps local tests and degraded startup
paths from crashing the pipeline if Redis is unavailable.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any

import redis

from app.config import settings

_lock = threading.Lock()
_task_runs: dict[str, dict[str, Any]] = {}
_redis_client: Any | None = None

TASK_KEY_PREFIX = "trend_scout:task_runs"
TASK_INDEX_KEY = f"{TASK_KEY_PREFIX}:index"
TASK_TTL_SECONDS = 60 * 60 * 24 * 14
TASK_INDEX_LIMIT = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _record_key(task_id: str) -> str:
    return f"{TASK_KEY_PREFIX}:{task_id}"


def _alias_key(run_id: str) -> str:
    return f"{TASK_KEY_PREFIX}:alias:{run_id}"


def _with_progress(run: dict[str, Any]) -> dict[str, Any]:
    total = int(run.get("total_steps") or 0)
    completed = int(run.get("completed_steps") or 0)
    if total > 0:
        run["progress"] = round(min(max(completed / total * 100, 0.0), 100.0), 1)
    else:
        run["progress"] = None
    return run


def _redis() -> Any | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if settings.service_env.lower() in {"test", "testing"}:
        return None
    try:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except redis.RedisError:
        _redis_client = None
        return None


def _save_to_memory(run: dict[str, Any]) -> None:
    with _lock:
        _task_runs[run["task_id"]] = dict(run)


def _save(run: dict[str, Any]) -> None:
    run = _with_progress(dict(run))
    client = _redis()
    if client is None:
        _save_to_memory(run)
        return

    payload = json.dumps(run)
    try:
        client.set(_record_key(run["task_id"]), payload, ex=TASK_TTL_SECONDS)
        run_id = run.get("run_id")
        if run_id:
            client.set(
                _alias_key(str(run_id)),
                json.dumps({"task_id": run["task_id"]}),
                ex=TASK_TTL_SECONDS,
            )
        client.zadd(TASK_INDEX_KEY, {run["task_id"]: float(run.get("sort_ts") or time.time())})
        if hasattr(client, "zremrangebyrank"):
            client.zremrangebyrank(TASK_INDEX_KEY, 0, -(TASK_INDEX_LIMIT + 1))
    except redis.RedisError:
        _save_to_memory(run)


def _load_from_memory(task_or_run_id: str) -> dict[str, Any] | None:
    with _lock:
        if task_or_run_id in _task_runs:
            return _with_progress(dict(_task_runs[task_or_run_id]))
        for run in _task_runs.values():
            if run.get("run_id") == task_or_run_id:
                return _with_progress(dict(run))
    return None


def _load(task_or_run_id: str) -> dict[str, Any] | None:
    client = _redis()
    if client is None:
        return _load_from_memory(task_or_run_id)

    try:
        task_id = task_or_run_id
        alias_payload = client.get(_alias_key(task_or_run_id))
        if alias_payload:
            task_id = str(json.loads(alias_payload).get("task_id") or task_or_run_id)
        payload = client.get(_record_key(task_id))
        if not payload:
            return _load_from_memory(task_or_run_id)
        return _with_progress(json.loads(payload))
    except redis.RedisError, json.JSONDecodeError, TypeError, ValueError:
        return _load_from_memory(task_or_run_id)


def create_task_run(
    task_id: str,
    trigger: str,
    total_steps: int,
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    _save(
        {
            "task_id": task_id,
            "run_id": run_id,
            "trigger": trigger,
            "total_steps": total_steps,
            "completed_steps": 0,
            "current_step": "created",
            "status": "pending",
            "created_at": _now_iso(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "sort_ts": time.time(),
            "metadata": metadata or {},
        }
    )


def start_task_run(task_id: str) -> None:
    run = _load(task_id)
    if not run:
        return
    run["status"] = "running"
    run["started_at"] = _now_iso()
    run["sort_ts"] = time.time()
    _save(run)


def update_task_progress(
    task_id: str,
    completed_steps: int | None = None,
    total_steps: int | None = None,
    current_step: str | None = None,
    status: str | None = None,
) -> None:
    run = _load(task_id)
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
    run["sort_ts"] = time.time()
    _save(run)


def complete_task_run(
    task_id: str,
    status: str = "success",
    error: str | None = None,
) -> None:
    run = _load(task_id)
    if not run:
        return
    run["status"] = status
    run["completed_at"] = _now_iso()
    run["error"] = error
    run["sort_ts"] = time.time()
    if status == "success":
        run["completed_steps"] = run.get("total_steps", run.get("completed_steps", 0))
    _save(run)


def get_task_run(task_id: str) -> dict[str, Any] | None:
    return _load(task_id)


def list_task_runs(limit: int = 25) -> list[dict[str, Any]]:
    client = _redis()
    if client is None:
        with _lock:
            runs = sorted(
                _task_runs.values(),
                key=lambda item: item.get("sort_ts", 0),
                reverse=True,
            )
            return [_with_progress(dict(r)) for r in runs[:limit]]

    try:
        task_ids = client.zrevrange(TASK_INDEX_KEY, 0, max(limit - 1, 0))
        runs = []
        for task_id in task_ids:
            run = _load(str(task_id))
            if run:
                runs.append(run)
        return runs
    except redis.RedisError:
        with _lock:
            runs = sorted(
                _task_runs.values(),
                key=lambda item: item.get("sort_ts", 0),
                reverse=True,
            )
            return [_with_progress(dict(r)) for r in runs[:limit]]
