from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.database import async_session_factory
from app.schemas.api import BacktestRunRequest, BacktestRunResponse
from app.security import SCOPE_READ, SCOPE_WRITE, verify_internal_token
from app.services.backtest import (
    run_backtest,
)
from app.services.calibration import (
    run_calibration as calibration_service,
)

router = APIRouter(
    prefix="",
    tags=["backtest", "calibration"],
    dependencies=[Depends(verify_internal_token)],
)


@router.post("/backtest/run", response_model=BacktestRunResponse)
async def run_backtest_route(
    request: BacktestRunRequest,
    _token: str = SCOPE_WRITE,
) -> BacktestRunResponse:
    """Run the backtest end-to-end and return the summary + predictions."""

    async def _provider(product_id: int, after: Any, days: int) -> dict[str, Any]:
        return {"quantity": 0, "revenue": 0.0, "order_count": 0}

    async with async_session_factory() as session:
        result = await run_backtest(
            session,
            lookback_reports=request.lookback_reports,
            sales_window_days=request.sales_window_days,
            actual_sales_provider=_provider,
        )
    if result.get("status") == "no_data":
        return BacktestRunResponse(
            status="no_data",
            report_count=0,
            summary={},
            predictions=[],
        )
    return BacktestRunResponse(
        status=result.get("status", "ok"),
        report_count=result.get("report_count", 0),
        summary=result.get("summary", {}),
        predictions=result.get("predictions", []),
    )


@router.post("/calibration/run")
async def run_calibration_route(
    _token: str = SCOPE_WRITE,
) -> dict[str, Any]:
    """Run the calibration (backtest + tuning hints) and persist a record."""
    async with async_session_factory() as session:
        record = await calibration_service(session, trigger="manual")
    return record


@router.get("/calibration/history")
async def calibration_history(_token: str = SCOPE_READ) -> dict[str, Any]:
    async with async_session_factory() as session:
        history = await calibration_service.get_calibration_history(session, limit=20)
    return {"items": history}
