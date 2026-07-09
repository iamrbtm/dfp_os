from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx
from flask import Response, current_app, jsonify, render_template, request

logger = logging.getLogger(__name__)

_spec_cache: dict = {
    "data": None,
    "fetched_at": 0,
    "source": None,
}


def _get_openapi_spec() -> dict | None:
    config = current_app.config
    now = time.time()
    refresh = config.get("DFPOS_OPENAPI_REFRESH_INTERVAL", 300)

    if _spec_cache["data"] is not None and (now - _spec_cache["fetched_at"]) < refresh:
        return _spec_cache["data"]

    url = config.get("DFPOS_OPENAPI_URL", "")
    fallback_path = config.get("DFPOS_OPENAPI_FALLBACK_PATH", "./openapi/openapi.json")

    if url:
        try:
            resp = httpx.get(url, timeout=10)
            resp.raise_for_status()
            _spec_cache["data"] = resp.json()
            _spec_cache["fetched_at"] = now
            _spec_cache["source"] = f"remote:{url}"
            logger.info("Fetched OpenAPI spec from %s", url)
            return _spec_cache["data"]
        except Exception as e:
            logger.warning("Failed to fetch OpenAPI spec from %s: %s", url, e)

    fallback = Path(fallback_path)
    if fallback.exists():
        try:
            with open(fallback, "r") as f:
                _spec_cache["data"] = json.load(f)
            _spec_cache["fetched_at"] = now
            _spec_cache["source"] = f"local:{fallback_path}"
            logger.info("Loaded OpenAPI spec from fallback %s", fallback_path)
            return _spec_cache["data"]
        except Exception as e:
            logger.warning("Failed to load fallback spec: %s", e)

    logger.error("No OpenAPI spec available (remote unreachable and no fallback)")
    return None


def _str_to_bool(val: str | None) -> bool:
    if val is None:
        return False
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _check_auth() -> bool:
    config = current_app.config
    username = config.get("DOCS_USERNAME", "")
    password = config.get("DOCS_PASSWORD", "")
    if config.get("DOCS_AUTH_REQUIRED") and (not username or not password):
        raise RuntimeError("Docs auth is required but DOCS_USERNAME/DOCS_PASSWORD are missing.")
    if not config.get("DOCS_AUTH_REQUIRED") and (not username or not password):
        return True

    auth = request.authorization
    return auth and auth.username == username and auth.password == password


def _auth_required() -> Response | None:
    config = current_app.config
    configured = config.get("DOCS_USERNAME", "") and config.get("DOCS_PASSWORD", "")
    if config.get("DOCS_AUTH_REQUIRED") and not configured:
        raise RuntimeError("Docs auth is required but DOCS_USERNAME/DOCS_PASSWORD are missing.")
    if not config.get("DOCS_AUTH_REQUIRED") and not configured:
        return None
    if not _check_auth():
        return _auth_response()
    return None


def _auth_response() -> Response:
    resp = jsonify({"error": "Authentication required"})
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Basic realm="DFP OS API Docs"'
    return resp


def health():
    spec = _get_openapi_spec()
    return jsonify(
        {
            "status": "ok" if spec else "degraded",
            "spec_loaded": spec is not None,
            "spec_source": _spec_cache.get("source"),
            "spec_fetched_at": _spec_cache.get("fetched_at"),
        }
    )


def index():
    auth_issue = _auth_required()
    if auth_issue:
        return auth_issue

    spec = _get_openapi_spec()
    if spec is None:
        return render_template("error.html", message="OpenAPI spec is not available."), 503

    spec_json = json.dumps(spec)
    app_name = current_app.config.get("APP_NAME", "API Reference")
    theme = current_app.config.get("REDOC_THEME", "light")
    page_title = _spec_metadata_title(spec) or app_name

    return render_template(
        "redoc.html",
        spec_json=spec_json,
        page_title=page_title,
        app_name=app_name,
        theme=theme,
    )


def openapi_json():
    spec = _get_openapi_spec()
    if spec is None:
        return jsonify({"error": "OpenAPI spec not available"}), 503
    return jsonify(spec)


def openapi_proxy():
    return openapi_json()


def _spec_metadata_title(spec: dict | None) -> str | None:
    if spec is None:
        return None
    info = spec.get("info", {})
    return info.get("title")
