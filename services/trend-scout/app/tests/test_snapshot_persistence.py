"""Tests for the snapshot + source-health persistence layer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.services.snapshot_persistence import (
    _parse_scraped_at,
    persist_snapshots,
    persist_source_health,
)


def test_parse_scraped_at_handles_empty() -> None:
    fallback = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _parse_scraped_at(None, fallback) == fallback
    assert _parse_scraped_at("", fallback) == fallback


def test_parse_scraped_at_handles_iso_with_z() -> None:
    fallback = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = _parse_scraped_at("2026-08-13T12:00:00Z", fallback)
    assert result.year == 2026
    assert result.month == 8
    assert result.day == 13
    assert result.tzinfo is not None


def test_parse_scraped_at_handles_naive_iso() -> None:
    fallback = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = _parse_scraped_at("2026-08-13T12:00:00", fallback)
    assert result.tzinfo == timezone.utc


def test_parse_scraped_at_handles_invalid() -> None:
    fallback = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _parse_scraped_at("not-a-date", fallback) == fallback


@pytest.mark.asyncio
async def test_persist_snapshots_writes_rows() -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    results = [
        {
            "source": "etsy",
            "keyword_or_category": "dragon",
            "scraped_at": "2026-08-13T00:00:00Z",
            "items": [{"title": "a"}, {"title": "b"}],
            "errors": [],
        },
        {
            "source": "etsy",
            "keyword_or_category": "fidget",
            "scraped_at": "2026-08-13T00:00:01Z",
            "items": [],
            "errors": ["HTTP 500"],
        },
    ]
    count = await persist_snapshots(session, results)
    assert count == 2
    session.add_all.assert_called_once()
    added = session.add_all.call_args[0][0]
    assert len(added) == 2
    assert added[0].source == "etsy"
    assert added[0].item_count == 2
    assert added[1].item_count == 0


@pytest.mark.asyncio
async def test_persist_source_health_writes_rows() -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    health = [
        {
            "source": "etsy",
            "status": "error",
            "item_count": 0,
            "error_message": "boom",
            "keyword": None,
            "metadata": {},
        },
        {"source": "makerworld", "status": "success", "item_count": 50, "keyword": "trending", "metadata": {"x": 1}},
    ]
    count = await persist_source_health(session, health, report_id=42)
    assert count == 2
    session.add_all.assert_called_once()
