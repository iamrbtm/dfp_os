"""Tests for the analysis orchestrator + AI provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_ai_provider_deterministic_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import ai_provider

    monkeypatch.setattr(ai_provider.settings, "openai_api_key", "")
    monkeypatch.setattr(ai_provider.settings, "ai_provider", "openai")
    import asyncio

    summary = asyncio.run(
        ai_provider.synthesize_report(
            top_opportunities=[{"title": "Dragon", "score": 90, "recommended_action": "print_now"}],
            growing=[{"name": "dragons"}],
            declining=[{"name": "fidgets"}],
        )
    )
    assert "deterministic" in summary.lower() or "top opportunities" in summary.lower()


@pytest.mark.asyncio
async def test_ai_provider_falls_back_to_deterministic_on_openai_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import ai_provider

    monkeypatch.setattr(ai_provider.settings, "openai_api_key", "key-present")
    monkeypatch.setattr(ai_provider.settings, "ai_provider", "openai")

    with patch("openai.AsyncOpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
        mock_openai.return_value = mock_client

        summary = await ai_provider.synthesize_report(
            top_opportunities=[{"title": "Dragon", "score": 90}],
            growing=[],
            declining=[],
        )
    assert "deterministic" in summary.lower() or "top" in summary.lower()


def test_ai_provider_openai_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import ai_provider

    monkeypatch.setattr(ai_provider.settings, "openai_api_key", "key-present")
    monkeypatch.setattr(ai_provider.settings, "ai_provider", "openai")
    monkeypatch.setattr(ai_provider.settings, "openai_model_trend_scout", "test-model")

    summary_text = "AI generated weekly report."

    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message.content = summary_text

    with patch("openai.AsyncOpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
        mock_openai.return_value = mock_client

        import asyncio

        summary = asyncio.run(
            ai_provider.synthesize_report(
                top_opportunities=[{"title": "Dragon", "score": 90}],
                growing=[],
                declining=[],
            )
        )
    assert summary == summary_text


def test_orchestrator_imports() -> None:
    """Verify the orchestrator module is importable and exposes run_analysis."""
    from app.services.analysis import orchestrator

    assert hasattr(orchestrator, "run_analysis")
    import inspect

    assert inspect.iscoroutinefunction(orchestrator.run_analysis)


def test_new_category_discovery_returns_stable_shape() -> None:
    import asyncio

    from app.services.analysis.new_category_discovery import discover_new_categories

    result = asyncio.run(discover_new_categories())
    assert "clusters" in result
    assert "total_clusters_found" in result
    assert "total_titles_analyzed" in result
    assert "notes" in result
    assert result["total_clusters_found"] == 0
    assert result["clusters"] == []
