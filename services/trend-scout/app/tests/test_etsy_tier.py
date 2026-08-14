"""Tests for Phase 9: Firecrawl Etsy throttled tier + compliance flow."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.compliance import (
    gate_etsy_opt_in,
    is_acknowledgment_valid,
    record_acknowledgment,
)
from app.sources import firecrawl as firecrawl_source


@pytest.fixture
def tmp_compliance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the compliance module at a temp dir."""
    monkeypatch.setattr(
        "app.compliance.default_compliance_path",
        lambda: tmp_path / "etsy_opt_in.json",
    )
    return tmp_path


def test_record_acknowledgment_creates_file(tmp_compliance: Path) -> None:
    path = tmp_compliance / "etsy_opt_in.json"
    written = record_acknowledgment(path=path, note="phase 9 test")
    assert written.exists()
    payload = json.loads(written.read_text())
    assert payload["note"] == "phase 9 test"
    assert "acknowledged_at" in payload


def test_is_acknowledgment_valid_passes_on_fresh(tmp_compliance: Path) -> None:
    path = tmp_compliance / "etsy_opt_in.json"
    record_acknowledgment(path=path, note="x")
    assert is_acknowledgment_valid(path) is True


def test_is_acknowledgment_valid_fails_on_old(tmp_compliance: Path) -> None:
    path = tmp_compliance / "etsy_opt_in.json"
    path.write_text(json.dumps({"acknowledged_at": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()}))
    assert is_acknowledgment_valid(path) is False


def test_is_acknowledgment_valid_fails_on_missing(tmp_compliance: Path) -> None:
    assert is_acknowledgment_valid(tmp_compliance / "missing.json") is False


def test_gate_passes_when_etsy_disabled(tmp_compliance: Path) -> None:
    allowed, err = gate_etsy_opt_in(False)
    assert allowed is True
    assert err is None


def test_gate_requires_compliance_when_etsy_enabled(tmp_compliance: Path) -> None:
    allowed, err = gate_etsy_opt_in(True)
    assert allowed is False
    assert err and "acknowledgment" in err


def test_gate_passes_with_fresh_compliance(tmp_compliance: Path) -> None:
    record_acknowledgment(
        path=tmp_compliance / "etsy_opt_in.json",
        note="phase 9",
    )
    allowed, err = gate_etsy_opt_in(True, compliance_path=tmp_compliance / "etsy_opt_in.json")
    assert allowed is True
    assert err is None


def test_etsy_target_is_throttled_and_requires_opt_in() -> None:
    target = firecrawl_source._etsy_target()
    assert target.key == "etsy"
    assert target.throttled is True
    assert target.require_explicit_opt_in is True
    assert target.rate_limit_seconds == 30.0
    assert target.pages_per_run == 20


def test_etsy_target_honors_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRECRAWL_ETSY_MIN_INTERVAL_SECONDS", "10")
    monkeypatch.setenv("FIRECRAWL_ETSY_MAX_PAGES_PER_RUN", "5")
    target = firecrawl_source._etsy_target()
    assert target.rate_limit_seconds == 10.0
    assert target.pages_per_run == 5


def test_etsy_should_run_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIRECRAWL_ALLOW_ETSY", raising=False)
    should, reason = firecrawl_source._etsy_should_run("seed")
    assert should is False
    assert reason == "opt_in_disabled"


def test_etsy_should_run_blocks_without_compliance(monkeypatch: pytest.MonkeyPatch, tmp_compliance: Path) -> None:
    monkeypatch.setenv("FIRECRAWL_ALLOW_ETSY", "true")
    monkeypatch.setattr(
        "app.compliance.default_compliance_path",
        lambda: tmp_compliance / "etsy_opt_in.json",
    )
    should, reason = firecrawl_source._etsy_should_run("seed")
    assert should is False
    assert reason == "compliance_missing"


def test_etsy_should_run_respects_min_days_gate(monkeypatch: pytest.MonkeyPatch, tmp_compliance: Path) -> None:
    record_acknowledgment(
        path=tmp_compliance / "etsy_opt_in.json",
        note="phase 9",
    )
    monkeypatch.setenv("FIRECRAWL_ALLOW_ETSY", "true")
    monkeypatch.setenv("FIRECRAWL_ETSY_MIN_DAYS_BETWEEN_RUNS", "7")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    monkeypatch.setenv("FIRECRAWL_ETSY_LAST_RUN_AT", yesterday)

    should, reason = firecrawl_source._etsy_should_run("seed")
    assert should is False
    assert "min_days_not_met" in reason


def test_etsy_should_run_passes_when_compliance_and_quiet_enough(
    monkeypatch: pytest.MonkeyPatch, tmp_compliance: Path
) -> None:
    record_acknowledgment(
        path=tmp_compliance / "etsy_opt_in.json",
        note="phase 9",
    )
    monkeypatch.setenv("FIRECRAWL_ALLOW_ETSY", "true")
    monkeypatch.setenv("FIRECRAWL_ETSY_MIN_DAYS_BETWEEN_RUNS", "7")
    monkeypatch.setenv("FIRECRAWL_ETSY_RUN_PROBABILITY", "1.0")
    monkeypatch.delenv("FIRECRAWL_ETSY_LAST_RUN_AT", raising=False)
    monkeypatch.setattr(
        "app.compliance.default_compliance_path",
        lambda: tmp_compliance / "etsy_opt_in.json",
    )

    should, reason = firecrawl_source._etsy_should_run("seed")
    assert should is True
    assert reason == "selected"


def test_etsy_should_run_is_deterministic_by_run_id(monkeypatch: pytest.MonkeyPatch, tmp_compliance: Path) -> None:
    record_acknowledgment(
        path=tmp_compliance / "etsy_opt_in.json",
        note="phase 9",
    )
    monkeypatch.setenv("FIRECRAWL_ALLOW_ETSY", "true")
    monkeypatch.setenv("FIRECRAWL_ETSY_RUN_PROBABILITY", "0.15")
    monkeypatch.delenv("FIRECRAWL_ETSY_LAST_RUN_AT", raising=False)
    monkeypatch.setattr(
        "app.compliance.default_compliance_path",
        lambda: tmp_compliance / "etsy_opt_in.json",
    )

    a_should, a_reason = firecrawl_source._etsy_should_run("seed-fixed")
    b_should, b_reason = firecrawl_source._etsy_should_run("seed-fixed")
    assert (a_should, a_reason) == (b_should, b_reason)


def test_fetch_firecrawl_etsy_returns_throttled_when_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_compliance: Path
) -> None:
    monkeypatch.setenv("FIRECRAWL_ENABLED", "true")
    monkeypatch.setenv("FIRECRAWL_ALLOW_ETSY", "false")
    monkeypatch.setattr(
        "app.compliance.default_compliance_path",
        lambda: tmp_compliance / "etsy_opt_in.json",
    )
    import requests

    results = firecrawl_source.fetch_firecrawl_etsy(requests.Session(), None)
    assert results
    assert results[0].metadata["throttled"] is True
    assert results[0].metadata["throttle_reason"] == "opt_in_disabled"


def test_fetch_firecrawl_etsy_runs_when_selected(monkeypatch: pytest.MonkeyPatch, tmp_compliance: Path) -> None:
    record_acknowledgment(
        path=tmp_compliance / "etsy_opt_in.json",
        note="phase 9",
    )
    monkeypatch.setenv("FIRECRAWL_ENABLED", "true")
    monkeypatch.setenv("FIRECRAWL_API_URL", "http://firecrawl:3002")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")
    monkeypatch.setenv("FIRECRAWL_ALLOW_ETSY", "true")
    monkeypatch.setenv("FIRECRAWL_ETSY_RUN_PROBABILITY", "1.0")
    monkeypatch.setenv("FIRECRAWL_ETSY_MIN_DAYS_BETWEEN_RUNS", "0")
    monkeypatch.setattr(
        "app.compliance.default_compliance_path",
        lambda: tmp_compliance / "etsy_opt_in.json",
    )

    captured = {"value": None}

    def fake_scrape(client, target_url, source, keyword, target_meta=None):
        captured["value"] = (source, keyword, target_url)

        return {
            "source": source,
            "keyword_or_category": keyword,
            "items": [{"title": "sample", "url": "https://etsy.com/x"}],
            "errors": [],
            "metadata": {"target_url": target_url},
        }

    fake_module = MagicMock()
    fake_module.scrape_trending = fake_scrape
    fake_module.FirecrawlClient = MagicMock()

    with patch.dict("sys.modules", {"services.firecrawl.firecrawl_client": fake_module}):
        import requests

        results = firecrawl_source.fetch_firecrawl_etsy(requests.Session(), None)
    assert captured["value"] is not None
    assert captured["value"][0] == "etsy"
    assert any(r.items for r in results)


def test_mark_etsy_ran_updates_env(monkeypatch: pytest.MonkeyPatch, tmp_compliance: Path) -> None:
    monkeypatch.delenv("FIRECRAWL_ETSY_LAST_RUN_AT", raising=False)
    firecrawl_source.mark_etsy_ran()
    assert "FIRECRAWL_ETSY_LAST_RUN_AT" in os.environ
    # Round-trip parsable as ISO
    datetime.fromisoformat(os.environ["FIRECRAWL_ETSY_LAST_RUN_AT"])
