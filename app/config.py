from __future__ import annotations

import os
from pathlib import Path
from decimal import Decimal

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
    SHOP_DEFAULT_SHIPPING_RATE = Decimal(os.getenv("SHOP_DEFAULT_SHIPPING_RATE", "6.95"))
    SHOP_DEFAULT_CURRENCY = os.getenv("SHOP_DEFAULT_CURRENCY", "USD")
    SHOP_VENMO_HANDLE = os.getenv("SHOP_VENMO_HANDLE", "@dudefishprinting")
    SHOP_SUPPORT_EMAIL = os.getenv("SHOP_SUPPORT_EMAIL", os.getenv("ADMIN_EMAIL", "admin@example.com"))
    SQUARE_ENVIRONMENT = os.getenv("SQUARE_ENVIRONMENT", "sandbox")
    SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")
    SQUARE_LOCATION_ID = os.getenv("SQUARE_LOCATION_ID")
    SQUARE_APPLICATION_ID = os.getenv("SQUARE_APPLICATION_ID")
    SQUARE_API_BASE_URL = os.getenv(
        "SQUARE_API_BASE_URL",
        "https://connect.squareup.com"
        if os.getenv("SQUARE_ENVIRONMENT") == "production"
        else "https://connect.squareupsandbox.com",
    )
    API_TITLE = "Dude Fish OS API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/api"
    OPENAPI_JSON_PATH = "openapi.json"
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    MIGRATIONS_DIR = str(BASE_DIR / "migrations")
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
