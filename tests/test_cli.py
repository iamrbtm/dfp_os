from __future__ import annotations

from pathlib import Path

from flask_migrate import upgrade

from app import create_app
from app.extensions import db
from app.models import User


def test_seed_admin_command_is_idempotent(app, runner):
    first_run = runner.invoke(args=["seed", "admin"])
    second_run = runner.invoke(args=["seed", "admin"])

    assert first_run.exit_code == 0
    assert second_run.exit_code == 0

    with app.app_context():
        users = db.session.query(User).all()
        assert len(users) == 1
        assert users[0].email == "admin@example.com"


def test_initial_migration_upgrades_successfully(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    upload_path = tmp_path / "uploads"
    app = create_app(
        "testing",
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "UPLOAD_FOLDER": str(upload_path),
            "MIGRATIONS_DIR": str(Path(__file__).resolve().parent.parent / "migrations"),
        },
    )

    with app.app_context():
        upgrade(directory=app.config["MIGRATIONS_DIR"])
        inspector = db.inspect(db.engine)
        assert "users" in inspector.get_table_names()
