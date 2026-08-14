"""Tests for app.services.trend_scout_proxy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.trend_scout_proxy import (
    TrendScoutProxy,
    TrendScoutUnavailable,
    get_trend_scout_proxy,
)


@pytest.fixture
def proxy() -> TrendScoutProxy:
    return TrendScoutProxy(base_url="http://test:8093", token="test-token")


def _make_response(status_code: int, body: dict | None = None, raises: Exception | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.content = b"" if body is None else b'{"x": 1}'
    if body is not None:
        response.json = lambda: body
    if raises is not None:
        response.json = MagicMock(side_effect=raises)
    return response


def test_get_returns_payload(proxy: TrendScoutProxy) -> None:
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.request = MagicMock(return_value=_make_response(200, {"items": [1, 2]}))

    with patch("app.services.trend_scout_proxy.httpx.Client", return_value=fake_client):
        result = proxy.get("/api/v1/reports")
    assert result == {"items": [1, 2]}


def test_get_raises_on_non_2xx(proxy: TrendScoutProxy) -> None:
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.request = MagicMock(return_value=_make_response(503))

    with patch("app.services.trend_scout_proxy.httpx.Client", return_value=fake_client):
        with pytest.raises(TrendScoutUnavailable):
            proxy.get("/api/v1/reports")


def test_get_raises_on_network_error(proxy: TrendScoutProxy) -> None:
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.request = MagicMock(side_effect=httpx.ConnectError("boom"))

    with patch("app.services.trend_scout_proxy.httpx.Client", return_value=fake_client):
        with pytest.raises(TrendScoutUnavailable):
            proxy.get("/api/v1/reports")


def test_post_with_json(proxy: TrendScoutProxy) -> None:
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.request = MagicMock(
        return_value=_make_response(202, {"accepted": True, "run_id": "r1"})
    )

    with patch("app.services.trend_scout_proxy.httpx.Client", return_value=fake_client):
        result = proxy.post("/api/v1/pipeline/run", json={"trigger": "test"})
    assert result["accepted"] is True
    args, kwargs = fake_client.request.call_args
    assert args[0] == "POST"
    assert args[1] == "/api/v1/pipeline/run"
    assert kwargs["json"] == {"trigger": "test"}


def test_reports_with_scores_joins_data(proxy: TrendScoutProxy) -> None:
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    responses = [
        _make_response(200, {"items": [{"id": 7, "report_date": "2026-08-13"}]}),
        _make_response(200, {"items": [{"id": 100, "keyword": "dragon"}]}),
    ]
    fake_client.request = MagicMock(side_effect=responses)

    with patch("app.services.trend_scout_proxy.httpx.Client", return_value=fake_client):
        reports = proxy.reports_with_scores()
    assert reports[0]["opportunity_scores"] == [{"id": 100, "keyword": "dragon"}]


def test_reports_with_scores_handles_opportunities_failure(proxy: TrendScoutProxy) -> None:
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.request = MagicMock(
        side_effect=[
            _make_response(200, {"items": [{"id": 7}]}),
            _make_response(503),
        ]
    )

    with patch("app.services.trend_scout_proxy.httpx.Client", return_value=fake_client):
        reports = proxy.reports_with_scores()
    assert reports[0]["opportunity_scores"] == []


def _fake_app(config: dict):
    class _FakeApp:
        def app_context(self_inner):
            class _Ctx:
                def __enter__(self2):
                    return self2

                def __exit__(self2, *exc):
                    return False

            return _Ctx()

    fake = _FakeApp()
    fake.config = dict(config)
    return fake


def test_get_trend_scout_proxy_reads_config() -> None:
    fake = _fake_app(
        {
            "TREND_SCOUT_SERVICE_URL": "http://from-config:9999",
            "TREND_SCOUT_INTERNAL_API_TOKEN": "config-token",
        }
    )
    with patch("app.services.trend_scout_proxy.current_app", fake):
        proxy = get_trend_scout_proxy()
    assert proxy.base_url == "http://from-config:9999"
    assert proxy.token == "config-token"


def test_get_trend_scout_proxy_raises_on_missing_token() -> None:
    fake = _fake_app(
        {
            "TREND_SCOUT_SERVICE_URL": "http://from-config:9999",
            "TREND_SCOUT_INTERNAL_API_TOKEN": "",
        }
    )
    with patch("app.services.trend_scout_proxy.current_app", fake):
        with pytest.raises(TrendScoutUnavailable):
            get_trend_scout_proxy()


def test_latest_report_returns_empty_on_unavailable(proxy: TrendScoutProxy) -> None:
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.request = MagicMock(return_value=_make_response(500))

    with patch("app.services.trend_scout_proxy.httpx.Client", return_value=fake_client):
        result = proxy.latest_report()
    assert result == {}


def test_save_weights_posts_entries(proxy: TrendScoutProxy) -> None:
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.request = MagicMock(return_value=_make_response(200, {"items": []}))

    entries = [{"group": "score", "key": "purchase_intent", "value": 0.5}]
    with patch("app.services.trend_scout_proxy.httpx.Client", return_value=fake_client):
        proxy.save_weights(entries)
    args, _kwargs = fake_client.request.call_args
    assert args[0] == "POST"
    assert args[1] == "/api/v1/weights/save"
