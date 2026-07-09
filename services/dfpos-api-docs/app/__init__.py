from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify

from app.config import Config

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app() -> Flask:
    load_dotenv(BASE_DIR / ".env")

    app = Flask(__name__)
    Config.validate()
    app.config.from_object(Config)

    logging.basicConfig(
        level=getattr(logging, app.config["LOG_LEVEL"], logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _register_routes(app)
    _register_error_handlers(app)
    _register_context_processors(app)

    return app


def _register_routes(app: Flask) -> None:
    from app.routes import health, index, openapi_json, openapi_proxy

    app.add_url_rule("/health", view_func=health)
    app.add_url_rule("/", view_func=index)
    app.add_url_rule("/openapi.json", view_func=openapi_json)
    app.add_url_rule("/api/v1/openapi.json", view_func=openapi_proxy)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(_):
        return jsonify({"error": "Internal server error"}), 500


def _register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_config():
        return {"config": app.config}
