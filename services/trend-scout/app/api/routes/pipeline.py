from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery
from app.database import async_session_factory
from app.schemas.api import (
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineStatusResponse,
)
from app.security import SCOPE_READ, SCOPE_WRITE, verify_internal_token
from app.workers.task_monitor import (
    create_task_run,
    get_task_run,
    list_task_runs,
    update_task_progress,
)

router = APIRouter(
    prefix="/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(verify_internal_token)],
)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


@router.post("/run", response_model=PipelineRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    request: PipelineRunRequest,
    _token: str = SCOPE_WRITE,
) -> PipelineRunResponse:
    """Enqueue a pipeline run on the ``trend_scout`` queue (low priority)."""
    run_id = request.run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%f")
    try:
        async_result = celery.send_task(
            "app.workers.tasks.trend_scout_pipeline",
            kwargs={"run_id": run_id, "trigger": request.trigger},
            queue="trend_scout",
            priority=1,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "enqueue_failed", "message": str(exc)},
        ) from exc
    create_task_run(
        task_id=async_result.id,
        trigger=request.trigger,
        total_steps=12,
        run_id=run_id,
        metadata={"source": "api"},
    )
    update_task_progress(async_result.id, current_step="queued", status="queued")
    return PipelineRunResponse(
        accepted=True,
        run_id=run_id,
        task_id=async_result.id,
        status="queued",
    )


@router.get("/status/{run_id}", response_model=PipelineStatusResponse)
async def run_status(
    run_id: str,
    _token: str = SCOPE_READ,
) -> PipelineStatusResponse:
    """Look up the latest task-run row for ``run_id`` (matches by prefix)."""
    runs = list_task_runs(limit=200)
    for run in runs:
        if run.get("run_id") == run_id or run.get("task_id") == run_id:
            return PipelineStatusResponse(
                run_id=run_id,
                state=run.get("status", "unknown"),
                completed_step=run.get("current_step"),
                progress=run.get("progress"),
            )
    return PipelineStatusResponse(
        run_id=run_id,
        state="unknown",
        completed_step=None,
        progress=None,
    )


@router.get("/runs")
async def task_runs(
    limit: int = 100,
    _token: str = SCOPE_READ,
) -> dict[str, list[dict]]:
    return {"items": list_task_runs(limit=limit)}


@router.get("/runs/{run_id}")
async def task_run_detail(
    run_id: str,
    _token: str = SCOPE_READ,
) -> dict:
    run = get_task_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "task_run_not_found", "message": f"No task run {run_id}."},
        )
    return run


@router.post("/cancel/{run_id}")
async def cancel_run(
    run_id: str,
    _token: str = SCOPE_WRITE,
) -> dict[str, str]:
    """Revoke a queued task by id (best-effort)."""
    run = get_task_run(run_id)
    task_id = str(run.get("task_id") if run else run_id)
    try:
        celery.control.revoke(task_id, terminate=False)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "cancel_failed", "message": str(exc)},
        ) from exc
    if run:
        update_task_progress(task_id, current_step="revoked", status="revoked")
    return {"run_id": run_id, "status": "revoked"}
