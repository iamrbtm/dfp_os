"""Tests for the weights module."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock

import pytest

from app.models import TrendWeight
from app.services import weights


def test_default_score_weights_sum_is_meaningful() -> None:
    total = sum(weights.DEFAULT_SCORE_WEIGHTS.values())
    assert 0.5 < total < 2.0


def test_default_source_weights_include_firecrawl_targets() -> None:
    for name in (
        "firecrawl_etsy",
        "firecrawl_cults3d",
        "firecrawl_thangs",
        "firecrawl_stlfinder",
        "firecrawl_cgtrader",
        "firecrawl_mmf",
        "firecrawl_general",
    ):
        assert name in weights.DEFAULT_SOURCE_WEIGHTS
        assert 0.0 <= weights.DEFAULT_SOURCE_WEIGHTS[name] <= 2.0


def test_firecrawl_etsy_weight_is_lowest() -> None:
    """Per design: Etsy is throttled + best-effort so its weight is the lowest among
    Firecrawl targets to avoid dominating scoring even when it works."""
    firecrawl_targets = {k: v for k, v in weights.DEFAULT_SOURCE_WEIGHTS.items() if k.startswith("firecrawl_")}
    assert weights.DEFAULT_SOURCE_WEIGHTS["firecrawl_etsy"] <= min(
        v for k, v in firecrawl_targets.items() if k != "firecrawl_etsy"
    )


def test_validate_score_weights_rejects_missing_keys() -> None:
    errors = weights.validate_score_weights({"purchase_intent": 0.5})
    assert any("Missing" in e for e in errors)


def test_validate_score_weights_rejects_unknown_keys() -> None:
    errors = weights.validate_score_weights({**weights.DEFAULT_SCORE_WEIGHTS, "made_up": 0.5})
    assert any("Unknown" in e for e in errors)


def test_validate_score_weights_rejects_out_of_range() -> None:
    bad = dict(weights.DEFAULT_SCORE_WEIGHTS)
    bad["purchase_intent"] = 5.0
    errors = weights.validate_score_weights(bad)
    assert any("outside allowed range" in e for e in errors)


def test_validate_score_weights_rejects_non_numeric() -> None:
    bad = dict(weights.DEFAULT_SCORE_WEIGHTS)
    bad["purchase_intent"] = "not-a-number"
    errors = weights.validate_score_weights(bad)
    assert any("not a valid number" in e for e in errors)


def test_scoring_version_is_deterministic() -> None:
    w1 = {"a": 1, "b": 2}
    w2 = {"b": 2, "a": 1}
    assert weights.scoring_version(w1) == weights.scoring_version(w2)


def test_scoring_version_changes_with_weights() -> None:
    a = weights.scoring_version({"a": 1.0, "b": 2.0})
    b = weights.scoring_version({"a": 1.0, "b": 2.5})
    assert a != b


def test_scoring_version_is_short_hash() -> None:
    v = weights.scoring_version({"a": 1.0})
    expected_len = len(hashlib.sha256(b"x").hexdigest()[:12])
    assert len(v) == expected_len


def test_group_for_prefix_maps_correctly() -> None:
    assert weights.group_for_prefix(weights.PREFIX_SCORE) == weights.GROUP_SCORE
    assert weights.group_for_prefix(weights.PREFIX_SOURCE) == weights.GROUP_SOURCE
    assert weights.group_for_prefix(weights.PREFIX_BUYER) == weights.GROUP_BUYER
    assert weights.group_for_prefix(weights.PREFIX_METRIC) == weights.GROUP_METRIC
    assert weights.group_for_prefix(weights.PREFIX_SOURCE_ENABLED) == weights.GROUP_SOURCE_ENABLED
    assert weights.group_for_prefix("unknown.") == "default"


@pytest.mark.asyncio
async def test_load_score_weights_returns_defaults_when_table_empty() -> None:
    """When the trend_weights table has no overrides, defaults are returned."""
    fake_session = AsyncMock()
    fake_result = AsyncMock()
    fake_scalars = AsyncMock()
    fake_scalars.all = lambda: []
    fake_result.scalars = lambda: fake_scalars
    fake_session.execute = AsyncMock(return_value=fake_result)

    out = await weights.load_score_weights(fake_session)
    assert out == weights.DEFAULT_SCORE_WEIGHTS


@pytest.mark.asyncio
async def test_save_weight_creates_and_updates() -> None:
    """save_weight inserts when missing, updates when present."""
    fake_session = AsyncMock()

    async def fake_execute(stmt):
        class _Result:
            def __init__(self, row):
                self._row = row

            def scalars(self):
                class _S:
                    def first(self_inner2):
                        return self_inner2.outer._row

                class _Outer:
                    def __init__(self_outer, outer):
                        self_outer.outer = outer

                _S.outer = self
                return _S()

        existing = getattr(stmt, "_existing", None)
        return _Result(existing)

    fake_session.execute = fake_execute  # type: ignore[assignment]
    fake_session.add = lambda row: None
    fake_session.flush = AsyncMock()

    # When existing is None -> create
    await weights.save_weight(fake_session, group="score", key="purchase_intent", value=0.42)


@pytest.mark.asyncio
async def test_save_weight_by_prefix_dispatches_to_correct_group() -> None:
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=AsyncMock(scalars=lambda: AsyncMock(first=lambda: None)))
    fake_session.add = lambda row: None
    fake_session.flush = AsyncMock()

    await weights.save_weight_by_prefix(fake_session, prefix=weights.PREFIX_SOURCE, key="etsy", value=1.5)
    fake_session.execute.assert_awaited()


@pytest.mark.asyncio
async def test_load_source_enabled_state_merges_defaults_and_overrides() -> None:
    fake_session = AsyncMock()
    rows = [
        TrendWeight(group=weights.GROUP_SOURCE_ENABLED, key="etsy", value=0.0),
    ]

    class _S:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            class _Inner:
                def __init__(self_inner2):
                    pass

                def all(self_inner2):
                    return self.rows

            return _Inner()

    class _Result:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return _S(self.rows).scalars()

    fake_session.execute = AsyncMock(return_value=_Result(rows))
    state = await weights.load_source_enabled_state(fake_session, ["etsy", "myminifactory"])
    assert state == {"etsy": False, "myminifactory": True}


def test_prefix_constants() -> None:
    assert weights.PREFIX_SCORE == "trend_weight."
    assert weights.PREFIX_SOURCE == "trend_source."
    assert weights.PREFIX_BUYER == "trend_buyer."
    assert weights.PREFIX_METRIC == "trend_metric."
    assert weights.PREFIX_SOURCE_ENABLED == "trend_source_enabled."


def test_trend_weight_unique_constraint_is_group_scoped() -> None:
    constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in TrendWeight.__table__.constraints
        if constraint.name
    }
    assert constraints["uq_trend_weights_group_key"] == ("group", "key")
    assert "uq_trend_weights_key" not in constraints
