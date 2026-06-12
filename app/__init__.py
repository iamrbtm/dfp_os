from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template

from app.blueprints.auth import bp as auth_bp
from app.blueprints.dashboard import bp as dashboard_bp
from app.blueprints.public import bp as public_bp
from app.cli import seed_group
from app.extensions import api, csrf, db, login_manager, migrate
from app.models import User

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(config_name: str | None = None, test_config: dict | None = None) -> Flask:
    load_dotenv(BASE_DIR / ".env")
    from app.config import config_by_name

    app = Flask(__name__, instance_relative_config=True)

    selected_config = config_name or os.getenv("FLASK_ENV", "development")
    app.config.from_object(config_by_name.get(selected_config, config_by_name["development"]))

    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    register_extensions(app)
    register_blueprints(app)
    register_cli(app)
    register_error_handlers(app)
    register_context_processors(app)

    return app


def register_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(
        app,
        db,
        directory=app.config["MIGRATIONS_DIR"],
        compare_type=True,
        render_as_batch=app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"),
    )
    login_manager.init_app(app)
    csrf.init_app(app)
    api.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        if not user_id.isdigit():
            return None
        return db.session.get(User, int(user_id))


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)


def register_cli(app: Flask) -> None:
    app.cli.add_command(seed_group)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(_: Exception):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def page_not_found(_: Exception):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(_: Exception):
        db.session.rollback()
        return render_template("errors/500.html"), 500


def register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_brand_context() -> dict[str, str]:
        return {
            "app_name": app.config["APP_NAME"],
        }
