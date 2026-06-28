from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import uuid

from flask import Flask, abort, g, jsonify, render_template, request
from flask_login import current_user

from app.blueprints.auth import bp as auth_bp
from app.blueprints.analytics import bp as analytics_bp
from app.blueprints.api import register_api_blueprints
from app.blueprints.api_tokens import bp as api_tokens_bp
from app.blueprints.audit_logs import bp as audit_logs_bp
from app.blueprints.cost_engine import bp as cost_engine_bp
from app.blueprints.customers import bp as customers_bp
from app.blueprints.expenses import bp as expenses_bp
from app.blueprints.custom_orders import bp as custom_orders_bp
from app.blueprints.dashboard import bp as dashboard_bp
from app.blueprints.markets import bp as markets_bp
from app.blueprints.inventory import bp as inventory_bp
from app.blueprints.orders import bp as orders_bp
from app.blueprints.pos import bp as pos_bp
from app.blueprints.prep_tasks import bp as prep_tasks_bp
from app.blueprints.print_jobs import bp as print_jobs_bp
from app.blueprints.printers import bp as printers_bp
from app.blueprints.products import bp as products_bp
from app.blueprints.public import bp as public_bp
from app.blueprints.receipts import bp as receipts_bp
from app.blueprints.settings import bp as settings_bp
from app.blueprints.trend_scout import bp as trend_scout_bp
from app.cli import migrate_group, seed_group
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
    Path(app.config["RECEIPT_STORAGE_PATH"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["MARKET_DOCUMENTS_PATH"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["PRODUCT_ASSETS_PATH"]).mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    register_extensions(app)
    register_blueprints(app)
    register_cli(app)
    register_request_guards(app)
    register_error_handlers(app)
    register_context_processors(app)

    return app


def register_extensions(app: Flask) -> None:
    from app.services.storage import bootstrap_object_storage

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

    from app.celery_app import make_celery
    import app.extensions as ext_mod

    ext_mod.celery = make_celery(app)

    with app.app_context():
        bootstrap_object_storage()

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        if not user_id.isdigit():
            return None
        return db.session.get(User, int(user_id))


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(public_bp)
    app.register_blueprint(receipts_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(printers_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(custom_orders_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(print_jobs_bp)
    app.register_blueprint(markets_bp)
    app.register_blueprint(prep_tasks_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(cost_engine_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(trend_scout_bp)
    app.register_blueprint(audit_logs_bp)
    app.register_blueprint(api_tokens_bp)
    register_api_blueprints(api)
    _register_redoc_view(app)


def _register_redoc_view(app: Flask) -> None:
    @app.route("/api/redoc")
    def redoc_ui():
        return render_template("api/redoc.html")


def register_request_guards(app: Flask) -> None:
    @app.before_request
    def assign_request_id_and_enforce_modules():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

        from app.module_registry import API_RESOURCE_TO_MODULE, BLUEPRINT_TO_MODULE, is_module_enabled
        from app.services.audit import record_audit_event

        module_key: str | None = None
        if request.path.startswith("/api/v1/"):
            parts = [part for part in request.path.removeprefix("/api/v1/").split("/") if part]
            if parts:
                resource = parts[0]
                if resource == "analytics" and len(parts) > 1:
                    resource = "analytics"
                elif resource == "exports" and len(parts) > 1:
                    export_name = parts[1].removesuffix(".csv")
                    resource = export_name
                module_key = API_RESOURCE_TO_MODULE.get(resource)
                module_key = module_key or "api"
        elif request.blueprint:
            module_key = BLUEPRINT_TO_MODULE.get(request.blueprint)

        if module_key and not is_module_enabled(module_key):
            record_audit_event(
                action="module.disabled_access_attempted",
                entity_type="module",
                entity_id=module_key,
                metadata={"path": request.path, "blueprint": request.blueprint},
                source_module=__name__,
            )
            if request.path.startswith("/api/"):
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "module_disabled",
                                "message": f"The {module_key} module is disabled.",
                                "details": {"module": module_key},
                            }
                        }
                    ),
                    403,
                )
            abort(403)

        if current_user and current_user.is_authenticated and module_key:
            g.active_module_key = module_key


def register_cli(app: Flask) -> None:
    app.cli.add_command(seed_group)
    app.cli.add_command(migrate_group)


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
    @app.template_filter("duration_minutes")
    def duration_minutes(value: object) -> str:
        try:
            total_minutes = int(round(float(value or 0)))
        except (TypeError, ValueError):
            total_minutes = 0

        days, remainder = divmod(total_minutes, 60 * 24)
        hours, minutes = divmod(remainder, 60)

        parts: list[str] = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)

    @app.context_processor
    def inject_brand_context() -> dict[str, object]:
        from flask_login import current_user
        from flask import request, url_for
        from app.theme_registry import ALL_THEMES
        from app.services.storefront import cart_item_count

        BLUEPRINT_SECTION_MAP: dict[str, str | None] = {
            "dashboard": "dashboard",
            "pos": "pos",
            "analytics": "analytics",
            "products": "products",
            "customers": "customers",
            "orders": "orders",
            "custom_orders": "custom_orders",
            "printers": "printers",
            "print_jobs": "print_jobs",
            "inventory": "inventory",
            "markets": "markets",
            "receipts": "expenses",
            "expenses": "expenses",
            "trend_scout": "trend_scout",
            "api_tokens": "api_tokens",
            "settings": "settings",
            "auth": None,
            "public": None,
            "api": None,
            "prep_tasks": "prep_tasks",
            "cost_engine": "cost_engine",
            "audit_logs": "audit_logs",
        }

        SECTION_TITLES: dict[str, str] = {
            "pos": "POS",
            "custom_orders": "Custom Orders",
            "print_jobs": "Print Jobs",
        }

        CONTEXT_NAV_ITEMS: dict[str, list[tuple[str, str]]] = {
            "analytics": [
                ("Overview", url_for("analytics.index")),
            ],
            "pos": [
                ("Sessions", url_for("pos.session_list")),
                ("New Session", url_for("pos.session_new")),
            ],
            "products": [
                ("Product Studio", url_for("products.studio")),
                ("Categories", url_for("products.list_resource", resource_key="categories")),
                ("Collections", url_for("products.list_resource", resource_key="collections")),
            ],
            "inventory": [
                ("Records", url_for("inventory.list_resource", resource_key="records")),
                ("Filament", url_for("inventory.list_resource", resource_key="filament-spools")),
                ("Locations", url_for("inventory.list_resource", resource_key="locations")),
            ],
            "printers": [
                ("Printers", url_for("printers.list_resource", resource_key="printers")),
                ("AMS Units", url_for("printers.list_resource", resource_key="ams-units")),
            ],
            "orders": [
                ("Orders", url_for("orders.list_resource", resource_key="orders")),
                ("Items", url_for("orders.list_resource", resource_key="items")),
                ("Payments", url_for("orders.list_resource", resource_key="payments")),
            ],
            "markets": [
                ("Markets", url_for("markets.list_resource", resource_key="markets")),
                ("New Market", url_for("markets.create_resource", resource_key="markets")),
                ("Packing List", url_for("markets.list_resource", resource_key="packing-lists")),
            ],
            "prep_tasks": [
                ("Tasks", url_for("prep_tasks.list_resource", resource_key="tasks")),
                ("Templates", url_for("prep_tasks.list_resource", resource_key="templates")),
            ],
            "cost_engine": [
                ("Overview", url_for("cost_engine.index")),
            ],
            "trend_scout": [
                ("Dashboard", url_for("trend_scout.index")),
            ],
            "audit_logs": [
                ("Audit Logs", url_for("audit_logs.index")),
            ],
            "expenses": [
                ("Receipts", url_for("receipts.dashboard")),
                ("Inbox", url_for("receipts.inbox")),
                ("Upload", url_for("receipts.upload")),
                ("Expenses", url_for("expenses.list_resource", resource_key="expenses")),
                ("New Expense", url_for("expenses.create_resource", resource_key="expenses")),
            ],
            "api_tokens": [
                ("API Tokens", url_for("api_tokens.list_tokens")),
                ("Create Token", url_for("api_tokens.create_token")),
            ],
            "settings": [
                ("Settings", url_for("settings.settings_list")),
                ("Themes", url_for("settings.themes")),
            ],
        }

        active_section: str | None = None
        bp_name: str | None = request.blueprint
        if bp_name:
            active_section = BLUEPRINT_SECTION_MAP.get(bp_name)

        context_title = SECTION_TITLES.get(active_section) if active_section else None
        context_nav_items = CONTEXT_NAV_ITEMS.get(active_section) if active_section else None

        ctx: dict[str, object] = {
            "app_name": app.config["APP_NAME"],
            "themes": ALL_THEMES,
            "active_section": active_section,
            "context_title": context_title,
            "context_nav_items": context_nav_items,
            "public_cart_count": cart_item_count(),
        }
        if current_user and current_user.is_authenticated and hasattr(current_user, "theme_slug"):
            ctx["active_theme"] = current_user.theme_slug
        else:
            ctx["active_theme"] = app.config.get("DEFAULT_THEME", "dfp-github-light")
        return ctx
