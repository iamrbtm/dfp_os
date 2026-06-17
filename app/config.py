from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    APP_NAME = os.getenv("APP_NAME", "Dude Fish OS")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'instance' / 'dfp_os.db').as_posix()}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    TEMPLATES_AUTO_RELOAD = True
    MAX_CONTENT_LENGTH_MB = int(os.getenv("MAX_CONTENT_LENGTH_MB", "16"))
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH_MB * 1024 * 1024
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-now")
    POS_CARD_PROCESSING_ENABLED = _as_bool(os.getenv("POS_CARD_PROCESSING_ENABLED"), False)
    POS_CARD_PROCESSOR = os.getenv("POS_CARD_PROCESSOR", "placeholder")
    API_TITLE = "Dude Fish OS API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/api"
    OPENAPI_JSON_PATH = "openapi.json"
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    MIGRATIONS_DIR = str(BASE_DIR / "migrations")
    RECEIPT_STORAGE_DRIVER = os.getenv("RECEIPT_STORAGE_DRIVER", "local")
    RECEIPT_STORAGE_PATH = os.getenv(
        "RECEIPT_STORAGE_PATH",
        str(BASE_DIR / "uploads" / "receipts"),
    )
    RECEIPT_MAX_UPLOAD_MB = int(os.getenv("RECEIPT_MAX_UPLOAD_MB", "25"))
    RECEIPT_ALLOWED_TYPES = os.getenv(
        "RECEIPT_ALLOWED_TYPES",
        "image/jpeg,image/png,image/heic,image/heif,application/pdf",
    )
    RECEIPT_OCR_PROVIDER = os.getenv("RECEIPT_OCR_PROVIDER", "paddleocr")
    RECEIPT_AI_PROVIDER = os.getenv("RECEIPT_AI_PROVIDER", "ollama")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_RECEIPT_MODEL = os.getenv("OLLAMA_RECEIPT_MODEL", "qwen2.5vl:7b")
    RECEIPT_ENABLE_API_FALLBACK = _as_bool(os.getenv("RECEIPT_ENABLE_API_FALLBACK"), False)
    RECEIPT_API_PROVIDER = os.getenv("RECEIPT_API_PROVIDER", "")
    TAGGUN_API_KEY = os.getenv("TAGGUN_API_KEY", "")
    MINDEE_API_KEY = os.getenv("MINDEE_API_KEY", "")
    VERYFI_CLIENT_ID = os.getenv("VERYFI_CLIENT_ID", "")
    VERYFI_CLIENT_SECRET = os.getenv("VERYFI_CLIENT_SECRET", "")
    RECEIPT_DUPLICATE_STRICTNESS = os.getenv("RECEIPT_DUPLICATE_STRICTNESS", "normal")
    RECEIPT_LOW_CONFIDENCE_THRESHOLD = float(os.getenv("RECEIPT_LOW_CONFIDENCE_THRESHOLD", "0.80"))

    AUDIT_LOG_BASE_URL = os.getenv("AUDIT_LOG_BASE_URL", "http://audit-log-service:8090")
    AUDIT_LOG_TOKEN = os.getenv("AUDIT_LOG_TOKEN", "")
    AUDIT_LOG_ENABLED = _as_bool(os.getenv("AUDIT_LOG_ENABLED"), False)

    DEFAULT_THEME = "dfp-github-light"


class DevelopmentConfig(Config):
    DEBUG = True
    ENVIRONMENT = "development"


class TestingConfig(Config):
    TESTING = True
    ENVIRONMENT = "testing"
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"


class ProductionConfig(Config):
    DEBUG = False
    ENVIRONMENT = "production"
    TEMPLATES_AUTO_RELOAD = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
