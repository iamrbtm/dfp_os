"""Trend Scout proxy — Flask-side helper that wraps the microservice HTTP API.

Replaces direct DB access in ``app.blueprints.trend_scout.routes``. The
microservice is the new source of truth for trend_reports / trend_snapshots /
trend_opportunity_scores / source_health_records / trend_weights / task-runs.

Usage::

    proxy = get_trend_scout_proxy()
    reports = proxy.list_reports(limit=25)

The proxy raises ``TrendScoutUnavailable`` when the microservice is unreachable
or returns a non-2xx status. Routes can fall back to a "trend scout offline"
template, or surface a flash message.

The ``httpx`` client uses sane defaults: 5-second timeout, no retries
(propagation is preferred so the admin UI doesn't sit on stale data).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from flask import current_app

logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT_SECONDS = 5.0


class TrendScoutUnavailable(Exception):
    """The microservice is unreachable, timed out, or returned a non-2xx."""


@dataclass
class TrendScoutProxy:
    base_url: str
    token: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def _client_ctx(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            with self._client_ctx() as client:
                response = client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("Trend Scout proxy error: %s %s -> %s", method, path, exc)
            raise TrendScoutUnavailable(str(exc)) from exc

        if response.status_code >= 400:
            raise TrendScoutUnavailable(f"{method} {path} -> HTTP {response.status_code}")

        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, json: dict | None = None, **kwargs: Any) -> dict[str, Any]:
        if json is not None:
            kwargs.setdefault("json", json)
        return self._request("POST", path, **kwargs)

    # --- Domain wrappers -------------------------------------------------

    def list_reports(self, limit: int = 25, offset: int = 0) -> dict[str, Any]:
        return self.get(
            "/api/v1/reports",
            params={"limit": limit, "offset": offset},
        )

    def latest_report(self) -> dict[str, Any]:
        try:
            return self.get("/api/v1/reports/latest")
        except TrendScoutUnavailable:
            return {}

    def report_by_id(self, report_id: int) -> dict[str, Any]:
        return self.get(f"/api/v1/reports/{report_id}")

    def reports_with_scores(self, limit: int = 25) -> list[dict[str, Any]]:
        """Return recent reports + their scores, joined client-side."""
        reports = self.list_reports(limit=limit).get("items", [])
        for rep in reports:
            try:
                scores = self.get(
                    "/api/v1/opportunities",
                    params={"report_id": rep["id"], "limit": 200},
                ).get("items", [])
            except TrendScoutUnavailable:
                scores = []
            rep["opportunity_scores"] = scores
        return reports

    def source_health(
        self,
        source: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if source:
            params["source"] = source
        if status:
            params["status"] = status
        return self.get("/api/v1/source-health", params=params)

    def latest_source_health(self) -> dict[str, Any]:
        return self.get("/api/v1/source-health/latest")

    def list_opportunities(
        self,
        report_id: int | None = None,
        source: str | None = None,
        action: str | None = None,
        include_dismissed: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "include_dismissed": "true" if include_dismissed else "false",
        }
        if report_id is not None:
            params["report_id"] = report_id
        if source:
            params["source"] = source
        if action:
            params["action"] = action
        return self.get("/api/v1/opportunities", params=params)

    def report_opportunities(
        self,
        report_id: int,
        action: str | None = None,
        include_dismissed: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        page = max(1, page)
        per_page = min(max(1, per_page), 200)
        return self.list_opportunities(
            report_id=report_id,
            action=action,
            include_dismissed=include_dismissed,
            limit=per_page,
            offset=(page - 1) * per_page,
        )

    def dismiss_opportunity(self, score_id: int) -> dict[str, Any]:
        return self.post(f"/api/v1/opportunities/{score_id}/dismiss")

    def undismiss_opportunity(self, score_id: int) -> dict[str, Any]:
        return self.post(f"/api/v1/opportunities/{score_id}/undismiss")

    def action_opportunity(self, score_id: int, action: str) -> dict[str, Any]:
        return self.post(
            f"/api/v1/opportunities/{score_id}/action",
            json={"action": action},
        )

    def weight_defaults(self) -> dict[str, Any]:
        return self.get("/api/v1/weights/defaults")

    def list_weights(self, group: str | None = None, limit: int = 200) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if group:
            params["group"] = group
        return self.get("/api/v1/weights", params=params)

    def save_weights(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        return self.post("/api/v1/weights/save", json={"entries": entries})

    def seed_default_weights(self) -> dict[str, Any]:
        return self.post("/api/v1/weights/seed-defaults")

    def run_pipeline(self, trigger: str = "manual", run_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"trigger": trigger}
        if run_id:
            body["run_id"] = run_id
        return self.post("/api/v1/pipeline/run", json=body)

    def pipeline_status(self, run_id: str) -> dict[str, Any]:
        return self.get(f"/api/v1/pipeline/status/{run_id}")

    def pipeline_cancel(self, run_id: str) -> dict[str, Any]:
        return self.post(f"/api/v1/pipeline/cancel/{run_id}")

    def task_runs(self, limit: int = 100) -> dict[str, Any]:
        return self.get("/api/v1/pipeline/runs", params={"limit": limit})

    def task_run(self, run_id: str) -> dict[str, Any]:
        return self.get(f"/api/v1/pipeline/runs/{run_id}")

    def calibration_history(self) -> dict[str, Any]:
        return self.get("/api/v1/calibration/history")

    def run_calibration(self) -> dict[str, Any]:
        return self.post("/api/v1/calibration/run")

    def run_backtest(
        self, lookback_reports: int = 12, sales_window_days: int = 60
    ) -> dict[str, Any]:
        return self.post(
            "/api/v1/backtest/run",
            json={
                "lookback_reports": lookback_reports,
                "sales_window_days": sales_window_days,
            },
        )

    def list_source_toggles(self) -> dict[str, Any]:
        return self.get("/api/v1/settings/source-toggles")

    def toggle_source(self, source: str, enabled: bool) -> dict[str, Any]:
        return self.post(
            "/api/v1/settings/source-toggles",
            json={"source": source, "enabled": enabled},
        )


def get_trend_scout_proxy() -> TrendScoutProxy:
    """Build a proxy instance from the current Flask app config."""
    base_url = current_app.config.get("TREND_SCOUT_SERVICE_URL", "http://trend-scout:8093")
    token = current_app.config.get("TREND_SCOUT_INTERNAL_API_TOKEN", "")
    if not token:
        raise TrendScoutUnavailable("TREND_SCOUT_INTERNAL_API_TOKEN not set in Flask app config")
    return TrendScoutProxy(base_url=base_url, token=token)
