from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


DEFAULT_TEST_DATABASE_URL = "mysql+pymysql://username:password@127.0.0.1:3306/dudefish_os_test"
DEFAULT_MIGRATION_DATABASE_URL = os.getenv(
    "MIGRATION_DATABASE_URL",
    "mysql+pymysql://username:password@127.0.0.1:3306/dudefish_os_migration_check",
)
DEFAULT_TEST_DATABASE_ADMIN_URL = os.getenv(
    "TEST_DATABASE_ADMIN_URL",
    "mysql+pymysql://root:rootpassword@127.0.0.1:3306/mysql",
)


def configured_test_database_url() -> str:
    return os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def migration_database_url() -> str:
    return os.getenv("MIGRATION_DATABASE_URL", DEFAULT_MIGRATION_DATABASE_URL)


def admin_database_url() -> str:
    return os.getenv("TEST_DATABASE_ADMIN_URL", DEFAULT_TEST_DATABASE_ADMIN_URL)


def _database_name(database_url: str) -> str:
    url = make_url(database_url)
    if not url.database:
        raise ValueError("Database URL must include a database name")
    return url.database


def _database_user(database_url: str) -> str | None:
    return make_url(database_url).username


def _database_password(database_url: str) -> str | None:
    return make_url(database_url).password


def _database_host_pattern(database_url: str) -> str:
    host = make_url(database_url).host or "%"
    return "%" if host in {"127.0.0.1", "localhost", "db"} else host


def ensure_database_exists(database_url: str) -> None:
    admin_url = admin_database_url()
    database_name = _database_name(database_url).replace("`", "``")
    username = _database_user(database_url)
    password = (_database_password(database_url) or "").replace("'", "''")
    host_pattern = _database_host_pattern(database_url).replace("'", "''")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            if username:
                connection.execute(
                    text(
                        f"GRANT ALL PRIVILEGES ON `{database_name}`.* "
                        f"TO '{username}'@'{host_pattern}' IDENTIFIED BY '{password}'"
                    )
                )
                connection.execute(text("FLUSH PRIVILEGES"))
    finally:
        engine.dispose()


def recreate_database(database_url: str) -> None:
    admin_url = admin_database_url()
    database_name = _database_name(database_url).replace("`", "``")
    username = _database_user(database_url)
    password = (_database_password(database_url) or "").replace("'", "''")
    host_pattern = _database_host_pattern(database_url).replace("'", "''")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
            connection.execute(
                text(
                    f"CREATE DATABASE `{database_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            if username:
                connection.execute(
                    text(
                        f"GRANT ALL PRIVILEGES ON `{database_name}`.* "
                        f"TO '{username}'@'{host_pattern}' IDENTIFIED BY '{password}'"
                    )
                )
                connection.execute(text("FLUSH PRIVILEGES"))
    finally:
        engine.dispose()


def base_test_app_config(tmp_path: Path, **overrides: object) -> dict[str, object]:
    upload_path = tmp_path / "uploads"
    receipt_path = tmp_path / "receipts"
    config: dict[str, object] = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": configured_test_database_url(),
        "UPLOAD_FOLDER": str(upload_path),
        "RECEIPT_STORAGE_PATH": str(receipt_path),
        "MARKET_DOCUMENTS_PATH": str(upload_path / "markets"),
        "PRODUCT_ASSETS_PATH": str(upload_path / "products"),
        "ADMIN_EMAIL": "admin@example.com",
        "ADMIN_PASSWORD": "change-me-now",
        "SERVER_NAME": "localhost.localdomain",
        "WTF_CSRF_ENABLED": False,
        "AUDIT_LOG_ENABLED": False,
        "FILE_STORAGE_BACKEND": "local",
        "RECEIPT_STORAGE_DRIVER": "local",
        "S3_AUTO_CREATE_BUCKETS": False,
        "CELERY_BROKER_URL": "memory://",
        "CELERY_RESULT_BACKEND": "cache+memory://",
    }
    config.update(overrides)
    return config
