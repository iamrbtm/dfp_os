from __future__ import annotations

from typing import Any

import httpx
from flask import current_app


class IntelligenceClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, enabled: bool = True):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.enabled = enabled

    def is_configured(self) -> bool:
        return bool(self.enabled and self.base_url and self.token)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.is_configured():
            return {"error": {"message": "DFPos Intelligence service is not configured."}}
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=15.0,
            ) as client:
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            current_app.logger.warning("intelligence service error: %s", exc)
            try:
                return {"error": exc.response.json()}
            except ValueError:
                return {"error": {"message": str(exc)}}
        except httpx.RequestError as exc:
            current_app.logger.warning("intelligence service unavailable: %s", exc)
            return {"error": {"message": str(exc)}}

    def health_ready(self) -> dict[str, Any]:
        return self._request("GET", "/health/ready")

    def product_summaries(self, limit: int = 10) -> dict[str, Any]:
        return self._request("GET", "/api/v1/warehouse/products", params={"limit": limit})

    def rebuild_square_warehouse(self) -> dict[str, Any]:
        return self._request("POST", "/api/v1/warehouse/rebuild-square")

    def ask(self, question: str, limit: int = 5) -> dict[str, Any]:
        return self._request("POST", "/api/v1/ask", json={"question": question, "limit": limit})

    def market_advisor(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/advisor/market", json=payload)

    def create_document(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/knowledge/documents", json=payload)

    def search_knowledge(self, query: str, limit: int = 5) -> dict[str, Any]:
        return self._request("GET", "/api/v1/knowledge/search", params={"q": query, "limit": limit})

    def record_outcome(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/decision-outcomes", json=payload)

    def decision_outcomes(self, limit: int = 25) -> dict[str, Any]:
        return self._request("GET", "/api/v1/decision-outcomes", params={"limit": limit})

    def legacy_import_all(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/imports/legacy-mariadb/import-all", json=payload)

    def legacy_list_tables(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/imports/legacy-mariadb/tables")

    def legacy_review_table(self, table_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/imports/legacy-mariadb/tables/{table_name}/review", json=payload)

    def legacy_delete_table_staging(self, table_name: str, confirm: bool = True) -> dict[str, Any]:
        return self._request("DELETE", f"/api/v1/imports/legacy-mariadb/tables/{table_name}/staging", params={"confirm": str(confirm).lower()})

    def legacy_upload_json(self, file_path: str) -> dict[str, Any]:
        import httpx
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "application/json")}
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=120.0,
            ) as client:
                response = client.post("/api/v1/imports/legacy-mariadb/upload-json", files=files)
                response.raise_for_status()
                return response.json()


def get_intelligence_client() -> IntelligenceClient:
    config = current_app.config
    return IntelligenceClient(
        base_url=config.get("INTELLIGENCE_SERVICE_URL", ""),
        token=config.get("INTELLIGENCE_INTERNAL_API_TOKEN", ""),
        enabled=config.get("INTELLIGENCE_ENABLED", True),
    )
