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
    list_task_runs,
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
            progress = 100.0 if run.get("status") == "success" else 0.0 if run.get("status") == "failed" else None
            return PipelineStatusResponse(
                run_id=run_id,
                state=run.get("status", "unknown"),
                completed_step=run.get("current_step"),
                progress=progress,
            )
    return PipelineStatusResponse(
        run_id=run_id,
        state="unknown",
        completed_step=None,
        progress=None,
    )


@router.post("/cancel/{run_id}")
async def cancel_run(
    run_id: str,
    _token: str = SCOPE_WRITE,
) -> dict[str, str]:
    """Revoke a queued task by id (best-effort)."""
    try:
        celery.control.revoke(run_id, terminate=False)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "cancel_failed", "message": str(exc)},
        ) from exc
    return {"run_id": run_id, "status": "revoked"}
