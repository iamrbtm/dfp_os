from __future__ import annotations

from typing import Any

import httpx
from flask import current_app


class SlicerClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, enabled: bool = True):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.enabled = enabled

    def is_configured(self) -> bool:
        return bool(self.enabled and self.base_url and self.token)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "DFPos Slicer service is not configured."}
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=600.0,
            ) as client:
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            current_app.logger.warning("slicer service error: %s", exc)
            try:
                return {"success": False, "error": exc.response.json()}
            except ValueError:
                return {"success": False, "error": str(exc)}
        except httpx.RequestError as exc:
            current_app.logger.warning("slicer service unavailable: %s", exc)
            return {"success": False, "error": str(exc)}

    def health_ready(self) -> dict[str, Any]:
        return self._request("GET", "/health/ready")

    def slice(
        self,
        model_file_path: str,
        profile_name: str | None = None,
        center: str | None = "128,128",
        slicer_options: dict | None = None,
        preserve_orientation: bool | None = None,
    ) -> dict[str, Any]:
        import json

        options_json = json.dumps(slicer_options) if slicer_options else None

        with open(model_file_path, "rb") as f:
            files = {"model_file": (model_file_path, f)}
            data = {}
            if profile_name:
                data["profile_name"] = profile_name
            if center is not None:
                data["center"] = center
            if slicer_options:
                data["slicer_options"] = options_json
            if preserve_orientation is not None:
                data["preserve_orientation"] = str(preserve_orientation).lower()
            return self._request("POST", "/api/v1/slice", files=files, data=data)


def get_slicer_client() -> SlicerClient:
    config = current_app.config
    return SlicerClient(
        base_url=config.get("SLICER_SERVICE_URL", ""),
        token=config.get("SLICER_INTERNAL_API_TOKEN", ""),
        enabled=config.get("SLICER_ENABLED", False),
    )
