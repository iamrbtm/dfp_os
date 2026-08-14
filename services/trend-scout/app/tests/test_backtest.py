"""Tests for the backtest + calibration services.

Verify:
- _rmse / _mae / _r2 / _precision_at_k math
- _generate_tuning_hints produces sensible suggestions
- run_backtest returns a no_data result when no reports exist
- run_calibration persists a record and includes the summary
- check_regression surfaces divergence between the latest two runs
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services import backtest, calibration


def _empty_session() -> AsyncMock:
    """Build a fake AsyncSession whose execute() returns scalars().all() == []."""
    fake_session = AsyncMock()

    class _Scalars:
        def scalars(self):
            class _S:
                def all(self):
                    return []

            return _S()

    class _Result:
        def scalars(self):
            return _Scalars().scalars()

    fake_session.execute = AsyncMock(return_value=_Result())
    return fake_session


def _session_returning_rows(rows: list[Any]) -> AsyncMock:
    """Build a fake session whose execute() returns the supplied rows."""
    fake_session = AsyncMock()

    class _S:
        def __init__(self, the_rows):
            self.the_rows = the_rows

        def all(self):
            return self.the_rows

    class _Scalars:
        def __init__(self, the_rows):
            self.the_rows = the_rows

        def scalars(self):
            return _S(self.the_rows)

    class _Result:
        def __init__(self, the_rows):
            self.the_rows = the_rows

        def scalars(self):
            return _Scalars(self.the_rows).scalars()

    fake_session.execute = AsyncMock(return_value=_Result(rows))
    return fake_session


def test_rmse_perfect_predictions_is_zero() -> None:
    assert backtest._rmse([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 0.0


def test_rmse_known_value() -> None:
    assert backtest._rmse([2.0], [0.0]) == 2.0


def test_rmse_empty_returns_zero() -> None:
    assert backtest._rmse([], []) == 0.0


def test_mae_perfect_is_zero() -> None:
    assert backtest._mae([1.0, 2.0], [1.0, 2.0]) == 0.0


def test_mae_known_value() -> None:
    assert backtest._mae([1.0, 2.0], [0.0, 5.0]) == 2.0


def test_r2_perfect_is_one() -> None:
    assert backtest._r2([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_r2_worse_than_mean_is_negative() -> None:
    assert backtest._r2([10.0, 10.0, 10.0], [1.0, 2.0, 3.0]) < 0.0


def test_r2_insufficient_data() -> None:
    assert backtest._r2([1.0], [1.0]) == 0.0


def test_precision_at_k_counts_hits() -> None:
    predictions = [
        {"actual_quantity_sold": 1},
        {"actual_quantity_sold": 0},
        {"actual_quantity_sold": 3},
        {"actual_quantity_sold": 0},
        {"actual_quantity_sold": 0},
    ]
    assert backtest._precision_at_k(predictions, k=5) == 0.4


def test_precision_at_k_zero_when_empty() -> None:
    assert backtest._precision_at_k([]) == 0.0


def test_tuning_hints_when_metrics_poor() -> None:
    poor = {
        "summary": {
            "rmse": 50.0,
            "mae": 0.5,
            "r2": -0.5,
            "top_hit_rate": 0.2,
        }
    }
    hints = backtest._generate_tuning_hints(poor)
    assert any("hit rate" in h for h in hints)
    assert any("RMSE" in h for h in hints)
    assert any("R^2" in h for h in hints)


def test_tuning_hints_when_metrics_strong() -> None:
    great = {
        "summary": {
            "rmse": 5.0,
            "mae": 0.1,
            "r2": 0.85,
            "top_hit_rate": 0.7,
        }
    }
    hints = backtest._generate_tuning_hints(great)
    assert hints == []


@pytest.mark.asyncio
async def test_run_backtest_returns_no_data_when_no_reports() -> None:
    fake_session = _empty_session()
    result = await backtest.run_backtest(fake_session)
    assert result["status"] == "no_data"
    assert result["report_count"] == 0


@pytest.mark.asyncio
async def test_check_regression_returns_none_with_no_history() -> None:
    fake_session = _empty_session()
    msg = await calibration.check_regression(fake_session)
    assert msg is None


@pytest.mark.asyncio
async def test_check_regression_surfaces_mae_increase() -> None:
    row1 = type(
        "_Row",
        (),
        {
            "key": "full",
            "group": "calibration_run:newer",
            "description": '{"trigger": "manual", "summary": {"mae": 0.3, "top_hit_rate": 0.6}}',
        },
    )()
    row2 = type(
        "_Row",
        (),
        {
            "key": "full",
            "group": "calibration_run:older",
            "description": '{"trigger": "manual", "summary": {"mae": 0.2, "top_hit_rate": 0.6}}',
        },
    )()
    fake_session = _session_returning_rows([row1, row2])
    msg = await calibration.check_regression(fake_session, threshold_mae_delta=0.05)
    assert msg and "MAE" in msg


@pytest.mark.asyncio
async def test_run_calibration_persists_record_even_with_no_data() -> None:
    """When no reports exist, run_calibration still persists a record."""
    fake_session = _empty_session()
    captured: dict[str, Any] = {}

    def fake_add(row: Any) -> None:
        captured["row"] = row

    fake_session.add = fake_add
    fake_session.commit = AsyncMock()

    record = await calibration.run_calibration(
        fake_session,
        trigger="manual",
        lookback_reports=4,
        sales_window_days=30,
    )
    assert record["status"] == "no_data"
    assert captured.get("row") is not None


@pytest.mark.asyncio
async def test_get_calibration_history_parses_description_json() -> None:
    row_payload = '{"trigger": "manual", "summary": {"mae": 0.3}}'
    fake_row = type(
        "_Row",
        (),
        {
            "key": "full",
            "group": "calibration_run:abc",
            "description": row_payload,
        },
    )()
    fake_session = _session_returning_rows([fake_row])
    history = await calibration.get_calibration_history(fake_session, limit=5)
    assert len(history) == 1
    assert history[0]["trigger"] == "manual"
    assert history[0]["_group"] == "calibration_run:abc"
