from __future__ import annotations

import os


class Config:
    DFPOS_OPENAPI_URL = os.getenv("DFPOS_OPENAPI_URL", "http://localhost:5000/api/openapi.json")
    DFPOS_OPENAPI_FALLBACK_PATH = os.getenv(
        "DFPOS_OPENAPI_FALLBACK_PATH", "./openapi/openapi.json"
    )
    DFPOS_OPENAPI_REFRESH_INTERVAL = int(os.getenv("DFPOS_OPENAPI_REFRESH_INTERVAL", "300"))

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8080"))

    DOCS_USERNAME = os.getenv("DOCS_USERNAME", "")
    DOCS_PASSWORD = os.getenv("DOCS_PASSWORD", "")
    DOCS_AUTH_REQUIRED_PATHS = os.getenv("DOCS_AUTH_REQUIRED_PATHS", "")

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-docs-secret")
    APP_NAME = os.getenv("APP_NAME", "Dude Fish OS API Reference")
    REDOC_THEME = os.getenv("REDOC_THEME", "light")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
