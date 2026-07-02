from __future__ import annotations

import os
from pathlib import Path
from decimal import Decimal

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DOCKER_DATABASE_URL = "mysql+pymysql://username:password@127.0.0.1:3306/dudefish_os"
DEFAULT_DOCKER_TEST_DATABASE_URL = (
    "mysql+pymysql://username:password@127.0.0.1:3306/dudefish_os_test"
)


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
        DEFAULT_DOCKER_DATABASE_URL,
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
    SHOP_DEFAULT_SHIPPING_RATE = Decimal(os.getenv("SHOP_DEFAULT_SHIPPING_RATE", "6.95"))
    SHOP_DEFAULT_CURRENCY = os.getenv("SHOP_DEFAULT_CURRENCY", "USD")
    SHOP_VENMO_HANDLE = os.getenv("SHOP_VENMO_HANDLE", "@dudefishprinting")
    SHOP_SUPPORT_EMAIL = os.getenv(
        "SHOP_SUPPORT_EMAIL", os.getenv("ADMIN_EMAIL", "admin@example.com")
    )
    SQUARE_ENVIRONMENT = os.getenv("SQUARE_ENVIRONMENT", "sandbox")
    SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")
    SQUARE_LOCATION_ID = os.getenv("SQUARE_LOCATION_ID")
    SQUARE_APPLICATION_ID = os.getenv("SQUARE_APPLICATION_ID")
    SQUARE_API_BASE_URL = os.getenv(
        "SQUARE_API_BASE_URL",
        (
            "https://connect.squareup.com"
            if os.getenv("SQUARE_ENVIRONMENT") == "production"
            else "https://connect.squareupsandbox.com"
        ),
    )
    API_TITLE = "Dude Fish OS API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/api"
    OPENAPI_JSON_PATH = "openapi.json"
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    OPENAPI_REDOC_PATH = "/redoc"
    OPENAPI_REDOC_URL = "https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"
    MIGRATIONS_DIR = str(BASE_DIR / "migrations")
    FILE_STORAGE_BACKEND = os.getenv(
        "FILE_STORAGE_BACKEND",
        os.getenv("RECEIPT_STORAGE_DRIVER", "local"),
    )
    RECEIPT_STORAGE_DRIVER = os.getenv("RECEIPT_STORAGE_DRIVER", "local")
    RECEIPT_STORAGE_PATH = os.getenv(
        "RECEIPT_STORAGE_PATH",
        str(BASE_DIR / "uploads" / "receipts"),
    )
    MARKET_DOCUMENTS_PATH = os.getenv(
        "MARKET_DOCUMENTS_PATH",
        str(BASE_DIR / "uploads" / "markets"),
    )
    PRODUCT_ASSETS_PATH = os.getenv(
        "PRODUCT_ASSETS_PATH",
        str(BASE_DIR / "uploads" / "products"),
    )
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "")
    S3_REGION = os.getenv("S3_REGION", "us-east-1")
    S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
    S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")
    S3_USE_SSL = _as_bool(os.getenv("S3_USE_SSL"), False)
    S3_AUTO_CREATE_BUCKETS = _as_bool(os.getenv("S3_AUTO_CREATE_BUCKETS"), True)
    RECEIPT_STORAGE_BUCKET = os.getenv("RECEIPT_STORAGE_BUCKET", "receipts")
    MARKET_DOCUMENTS_BUCKET = os.getenv("MARKET_DOCUMENTS_BUCKET", "markets")
    PRODUCT_ASSETS_BUCKET = os.getenv("PRODUCT_ASSETS_BUCKET", "products")
    RECEIPT_MAX_UPLOAD_MB = int(os.getenv("RECEIPT_MAX_UPLOAD_MB", "25"))
    RECEIPT_ALLOWED_TYPES = os.getenv(
        "RECEIPT_ALLOWED_TYPES",
        "image/jpeg,image/png,image/heic,image/heif,application/pdf",
    )
    RECEIPT_OCR_PROVIDER = os.getenv("RECEIPT_OCR_PROVIDER", "paddleocr")
    RECEIPT_AI_PROVIDER = os.getenv("RECEIPT_AI_PROVIDER", "openai")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_MODEL_RECEIPTS = os.getenv("OPENAI_MODEL_RECEIPTS", OPENAI_MODEL)
    OPENAI_MODEL_ANALYTICS = os.getenv("OPENAI_MODEL_ANALYTICS", OPENAI_MODEL)
    OPENAI_MODEL_TREND_SCOUT = os.getenv(
        "OPENAI_MODEL_TREND_SCOUT",
        os.getenv("OPENAI_MODEL_ANALYTICS", OPENAI_MODEL),
    )
    AI_RECEIPT_PARSING_ENABLED = _as_bool(os.getenv("AI_RECEIPT_PARSING_ENABLED"), False)
    AI_ANALYTICS_INSIGHTS_ENABLED = _as_bool(os.getenv("AI_ANALYTICS_INSIGHTS_ENABLED"), False)
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_FALLBACK_URL = os.getenv("OLLAMA_FALLBACK_URL", "http://localhost:11434")
    OLLAMA_RECEIPT_MODEL = os.getenv("OLLAMA_RECEIPT_MODEL", "llama3")
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
    AUDIT_LOG_FAIL_CLOSED = _as_bool(os.getenv("AUDIT_LOG_FAIL_CLOSED"), False)
    ALLOW_NEGATIVE_INVENTORY = _as_bool(os.getenv("ALLOW_NEGATIVE_INVENTORY"), False)
    INTELLIGENCE_ENABLED = _as_bool(os.getenv("INTELLIGENCE_ENABLED"), True)
    INTELLIGENCE_SERVICE_URL = os.getenv("INTELLIGENCE_SERVICE_URL", "http://localhost:8091")
    INTELLIGENCE_INTERNAL_API_TOKEN = os.getenv("INTELLIGENCE_INTERNAL_API_TOKEN", "")
    WEATHER_USER_AGENT = os.getenv(
        "WEATHER_USER_AGENT",
        f"{APP_NAME} ({ADMIN_EMAIL})",
    )

    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

    DEFAULT_THEME = "dfp-github-light"


class DevelopmentConfig(Config):
    DEBUG = True
    ENVIRONMENT = "development"


class TestingConfig(Config):
    TESTING = True
    ENVIRONMENT = "testing"
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", DEFAULT_DOCKER_TEST_DATABASE_URL)


class ProductionConfig(Config):
    DEBUG = False
    ENVIRONMENT = "production"
    TEMPLATES_AUTO_RELOAD = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
