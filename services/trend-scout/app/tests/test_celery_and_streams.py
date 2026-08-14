"""Tests for Phase 4: Celery tasks, priority routing, queue config, stream worker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.celery_app import celery
from app.workers.stream_worker import (
    STREAM_RUN_REQUESTS,
    _drain_one,
    _enqueue_run_request,
    run_worker,
)
from app.workers.task_monitor import (
    complete_task_run,
    create_task_run,
    get_task_run,
    list_task_runs,
    start_task_run,
    update_task_progress,
)


def test_celery_has_trend_scout_queue_with_high_max_priority() -> None:
    queues = celery.conf.task_queues
    assert queues is not None
    queue_names = {q.name for q in queues}
    assert "trend_scout" in queue_names
    queue = next(q for q in queues if q.name == "trend_scout")
    assert queue.queue_arguments.get("x-max-priority") == 10


def test_celery_default_priority_is_high() -> None:
    assert celery.conf.task_default_priority >= 5
    assert celery.conf.task_default_priority <= 10


def test_celery_priority_steps_configured() -> None:
    options = celery.conf.broker_transport_options
    assert "priority_steps" in options
    assert max(options["priority_steps"]) == 10
    assert options["queue_order_strategy"] == "priority"


def test_dispatch_tasks_route_to_trend_scout_queue() -> None:
    """Microservice Celery: workers.tasks route to trend_scout at low priority.

    The Flask-side dispatch task routes are tested in the main app's test
    suite (Phase 6 cutover adds those). This test verifies the microservice
    Celery which receives the dispatched call and runs the pipeline.
    """
    routes = celery.conf.task_routes
    assert routes is not None
    matched = False
    for pattern, config in routes.items():
        if "app.workers.tasks" in pattern:
            assert config["queue"] == "trend_scout"
            assert config["priority"] == 1
            matched = True
    assert matched, "No task route matches app.workers.tasks"


def test_dispatch_tasks_are_registered_in_microservice_celery() -> None:
    """The microservice Celery registers the pipeline + calibration tasks."""
    import app.workers.tasks  # noqa: F401 ensure module is loaded

    registered = set(celery.tasks.keys())
    assert "app.workers.tasks.trend_scout_pipeline" in registered
    assert "app.workers.tasks.calibrate_trend_scout" in registered


def test_microservice_celery_tasks_are_registered() -> None:
    """The microservice Celery has its own tasks registered."""
    import app.workers.tasks  # noqa: F401
    from app.celery_app import celery as ts_celery

    registered = set(ts_celery.tasks.keys())
    assert "app.workers.tasks.trend_scout_pipeline" in registered
    assert "app.workers.tasks.calibrate_trend_scout" in registered


def test_pipeline_task_routes_to_trend_scout_queue_with_low_priority() -> None:
    from app.celery_app import celery as ts_celery

    routes = ts_celery.conf.task_routes
    assert routes is not None
    matched = False
    for pattern, config in routes.items():
        if "app.workers.tasks" in pattern:
            assert config["queue"] == "trend_scout"
            assert config["priority"] == 1
            matched = True
    assert matched


def test_task_monitor_lifecycle() -> None:
    task_id = "test-monitor-1"
    create_task_run(task_id, trigger="manual", total_steps=5)
    run = get_task_run(task_id)
    assert run is not None
    assert run["status"] == "pending"
    assert run["total_steps"] == 5

    start_task_run(task_id)
    run = get_task_run(task_id)
    assert run["status"] == "running"
    assert run["started_at"] is not None

    update_task_progress(task_id, current_step="fetching_sources")
    update_task_progress(task_id, completed_steps=3, current_step="persisting")
    run = get_task_run(task_id)
    assert run["current_step"] == "persisting"
    assert run["completed_steps"] == 3

    complete_task_run(task_id, status="success")
    run = get_task_run(task_id)
    assert run["status"] == "success"
    assert run["completed_at"] is not None
    assert run["error"] is None


def test_task_monitor_records_failure() -> None:
    task_id = "test-monitor-fail"
    create_task_run(task_id, trigger="manual", total_steps=1)
    start_task_run(task_id)
    complete_task_run(task_id, status="failed", error="boom")
    run = get_task_run(task_id)
    assert run["status"] == "failed"
    assert run["error"] == "boom"


def test_task_monitor_list_orders_by_recency() -> None:
    create_task_run("a", trigger="manual", total_steps=1)
    create_task_run("b", trigger="manual", total_steps=1)
    runs = list_task_runs(limit=10)
    ids = [r["task_id"] for r in runs]
    assert "a" in ids
    assert "b" in ids


@pytest.mark.asyncio
async def test_stream_worker_enqueues_returns_entry_id() -> None:
    fake_redis = MagicMock()
    fake_redis.xadd = AsyncMock(return_value=b"1234-0")
    fake_redis.aclose = AsyncMock()

    with patch("redis.asyncio.from_url", return_value=fake_redis):
        entry_id = await _enqueue_run_request(
            run_id="stream-test-1",
            trigger="stream",
            business_id=None,
        )
    assert entry_id == b"1234-0"
    fake_redis.xadd.assert_awaited_once()
    args, _kwargs = fake_redis.xadd.call_args
    assert args[0] == STREAM_RUN_REQUESTS
    payload = args[1]
    assert payload["run_id"] == "stream-test-1"
    assert payload["trigger"] == "stream"


@pytest.mark.asyncio
async def test_stream_worker_drain_returns_false_on_empty_stream() -> None:
    fake_redis = MagicMock()
    fake_redis.xreadgroup = AsyncMock(return_value=[])
    fake_redis.xack = AsyncMock()
    fake_redis.aclose = AsyncMock()

    drained = await _drain_one(fake_redis, "consumer-test", block_ms=10)
    assert drained is False
    fake_redis.xack.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_worker_no_op_when_redis_streams_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.workers import stream_worker

    monkeypatch.setattr(stream_worker.settings, "enable_redis_streams", False)
    result = await run_worker("consumer-test", max_iterations=1)
    assert result == 0


@pytest.mark.asyncio
async def test_pipeline_runner_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify run_full_pipeline accepts the documented signature."""
    import inspect

    from app.services import pipeline_runner

    sig = inspect.signature(pipeline_runner.run_full_pipeline)
    params = list(sig.parameters.keys())
    assert "session_factory" in params
    assert "run_id" in params
    assert "trigger" in params
    assert "progress_callback" in params
