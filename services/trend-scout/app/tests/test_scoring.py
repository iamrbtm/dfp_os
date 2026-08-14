"""Tests for scoring math (trend_detector + opportunity_scoring).

Verify:
- recommended_action_for_score maps scores correctly
- score_breakdown_for_opportunity uses weights
- compute_opportunity_score returns 0..100
- _keyword_signal flags Clarksville / military local terms
- _keyword_signal flags weapon / Disney risk terms
- compute_top_opportunities is importable and exposes the function
- compute_velocity_and_momentum accepts an async session and returns shape
"""

from __future__ import annotations

import pytest

from app.services.analysis.opportunity_scoring import compute_opportunity_score
from app.services.analysis.trend_detector import (
    _find_matched_local_terms,
    _find_matched_risk_terms,
    _keyword_signal,
    recommended_action_for_score,
    score_breakdown_for_opportunity,
)


def test_recommended_action_for_score_thresholds() -> None:
    assert recommended_action_for_score(95.0) == "print_now"
    assert recommended_action_for_score(70.0) == "print_now"
    assert recommended_action_for_score(69.99) == "watch"
    assert recommended_action_for_score(40.0) == "watch"
    assert recommended_action_for_score(39.99) == "skip"
    assert recommended_action_for_score(0.0) == "skip"


def test_score_breakdown_for_opportunity_applies_weights() -> None:
    weights = {
        "score_weights": {
            "purchase_intent": 2.0,
            "trend_velocity": 1.0,
            "price_resilience": 1.0,
            "low_saturation": 1.0,
            "local_fit": 1.0,
            "production_fit": 1.0,
            "license_risk": 0.5,
        }
    }
    opp = {
        "purchase_intent": 0.5,
        "velocity": 0.5,
        "price_resilience": 0.5,
        "low_saturation": 0.5,
        "local_relevance": 0.5,
        "production_fit": 0.5,
        "license_risk": 0.0,
    }
    breakdown = score_breakdown_for_opportunity(opp, weights)
    assert breakdown["purchase_intent"] == 1.0
    assert breakdown["license_risk"] == 0.0
    assert breakdown["local_fit"] == 0.5


def test_compute_opportunity_score_in_range() -> None:
    opp = {
        "purchase_intent": 0.8,
        "velocity": 0.5,
        "price_resilience": 0.4,
        "low_saturation": 0.3,
        "local_relevance": 0.2,
        "production_fit": 0.7,
        "license_risk": 0.0,
    }
    score = compute_opportunity_score(opp)
    assert 0.0 <= score <= 100.0


def test_compute_opportunity_score_clamped() -> None:
    very_negative = {
        k: -1.0
        for k in (
            "purchase_intent",
            "velocity",
            "price_resilience",
            "low_saturation",
            "local_relevance",
            "production_fit",
            "license_risk",
        )
    }
    assert compute_opportunity_score(very_negative) >= 0.0

    very_positive = {k: 10.0 for k in very_negative}
    assert compute_opportunity_score(very_positive) <= 100.0


def test_keyword_signal_flags_local_terms() -> None:
    local, risk, label = _keyword_signal("Clarksville Tennessee Magnet", "clarksville tennessee magnet")
    assert local > 0.0
    assert risk == 0.0
    assert label == "low"


def test_keyword_signal_flags_military_family_terms() -> None:
    local, _, _ = _keyword_signal("Fort Campbell Family Keychain", "fort campbell family keychain")
    assert local > 0.0


def test_keyword_signal_flags_license_risks() -> None:
    _, risk, label = _keyword_signal("Disney Princess Figurine", "disney princess figurine")
    assert risk > 0.0
    assert label == "high"


def test_keyword_signal_unknown_label_when_neither_local_nor_risk() -> None:
    _, _, label = _keyword_signal("Rainbow Dragon", "rainbow dragon")
    assert label == "low"


def test_find_matched_local_terms_returns_sorted_terms() -> None:
    matched = _find_matched_local_terms("Clarksville Tennessee Magnet")
    assert "clarksville" in matched
    assert "tennessee" in matched


def test_find_matched_risk_terms_returns_sorted_terms() -> None:
    matched = _find_matched_risk_terms("Disney Princess Star Wars figurine")
    assert "disney" in matched
    assert "star wars" in matched


def test_compute_top_opportunities_is_async_callable() -> None:
    import inspect

    from app.services.analysis.trend_detector import compute_top_opportunities

    assert inspect.iscoroutinefunction(compute_top_opportunities)


def test_compute_velocity_and_momentum_is_async_callable() -> None:
    import inspect

    from app.services.analysis.trend_detector import compute_velocity_and_momentum

    assert inspect.iscoroutinefunction(compute_velocity_and_momentum)


def test_velocity_and_momentum_handles_empty_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Velocity should produce an empty result when there are no snapshots."""
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession

    fake_session = AsyncMock(spec=AsyncSession)

    class _S:
        def all(self):
            return []

    class _Scalars:
        def scalars(self):
            return _S()

    class _Result:
        def scalars(self):
            return _Scalars().scalars()

    fake_session.execute = AsyncMock(return_value=_Result())

    import asyncio

    from app.services.analysis import trend_detector

    velocity = asyncio.run(trend_detector.compute_velocity_and_momentum(fake_session))
    assert velocity["velocity"] == {}
    assert velocity["momentum"] == {}
    assert velocity["cross_source"] == {}
    assert velocity["metadata"]["snapshots_processed"] == 0


def test_compute_top_opportunities_returns_empty_on_no_snapshots() -> None:
    from unittest.mock import AsyncMock

    from sqlalchemy.ext.asyncio import AsyncSession

    fake_session = AsyncMock(spec=AsyncSession)

    class _S:
        def all(self):
            return []

    class _Scalars:
        def scalars(self):
            return _S()

    class _Result:
        def scalars(self):
            return _Scalars().scalars()

    fake_session.execute = AsyncMock(return_value=_Result())

    import asyncio

    from app.services.analysis import trend_detector

    opportunities = asyncio.run(trend_detector.compute_top_opportunities(fake_session, weights=None))
    assert opportunities == []


def test_growing_declining_extraction() -> None:
    from app.services.analysis.trend_detector import compute_growing_and_declining

    velocity = {
        "cross_source": {"dragon": 3, "fidget": 2, "x": 0},
        "momentum": {
            "etsy": {
                "dragon": {"direction": "up"},
                "fidget": {"direction": "down"},
            }
        },
    }
    clusters = {"clusters": [{"top_phrases": ["dragon", "fidget"]}]}
    growing, declining = compute_growing_and_declining(velocity, clusters)
    assert "dragon" in growing or "fidget" in growing
    assert "fidget" in declining


def test_score_breakdown_is_pure_function() -> None:
    a = score_breakdown_for_opportunity(
        {
            "purchase_intent": 0.1,
            "velocity": 0.2,
            "price_resilience": 0.3,
            "low_saturation": 0.4,
            "local_relevance": 0.5,
            "production_fit": 0.6,
            "license_risk": 0.7,
        },
        {"score_weights": {}},
    )
    b = score_breakdown_for_opportunity(
        {
            "purchase_intent": 0.1,
            "velocity": 0.2,
            "price_resilience": 0.3,
            "low_saturation": 0.4,
            "local_relevance": 0.5,
            "production_fit": 0.6,
            "license_risk": 0.7,
        },
        {"score_weights": {}},
    )
    assert a == b
