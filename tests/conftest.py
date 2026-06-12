from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import User, UserRole


@pytest.fixture()
def app(tmp_path: Path):
    database_path = tmp_path / "test.db"
    upload_path = tmp_path / "uploads"

    app = create_app(
        "testing",
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "UPLOAD_FOLDER": str(upload_path),
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "change-me-now",
            "SERVER_NAME": "localhost.localdomain",
        },
    )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


@pytest.fixture()
def admin_user(app):
    with app.app_context():
        user = User(
            email="owner@example.com",
            first_name="Dude",
            last_name="Fish",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("super-secret")
        db.session.add(user)
        db.session.commit()
        return {
            "email": user.email,
            "password": "super-secret",
            "id": user.id,
        }
