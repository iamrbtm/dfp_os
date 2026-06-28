from __future__ import annotations

from pathlib import Path

from flask_migrate import upgrade

from app import create_app
from app.extensions import db
from app.models import User
from tests.db_support import base_test_app_config, migration_database_url, recreate_database


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
    database_url = migration_database_url()
    recreate_database(database_url)
    app = create_app(
        "testing",
        base_test_app_config(
            tmp_path,
            SQLALCHEMY_DATABASE_URI=database_url,
            MIGRATIONS_DIR=str(Path(__file__).resolve().parent.parent / "migrations"),
        ),
    )

    with app.app_context():
        upgrade(directory=app.config["MIGRATIONS_DIR"])
        inspector = db.inspect(db.engine)
        assert "users" in inspector.get_table_names()
        assert "products" in inspector.get_table_names()
        assert "categories" in inspector.get_table_names()


def test_seed_demo_command_is_idempotent(app, runner):
    first_run = runner.invoke(args=["seed", "demo"])
    second_run = runner.invoke(args=["seed", "demo"])

    assert first_run.exit_code == 0
    assert second_run.exit_code == 0
    assert "Demo seed complete." in first_run.output

    with app.app_context():
        from app.models import Category, Printer, Product

        assert Category.query.count() >= 8
        assert Product.query.count() >= 13
        assert Printer.query.count() == 8
