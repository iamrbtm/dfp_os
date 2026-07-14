from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import FeatureFlag, Setting


HealthCheck = Callable[[], tuple[bool, str]]


def _healthy() -> tuple[bool, str]:
    return True, "ok"


@dataclass(frozen=True)
class NavEntry:
    label: str
    endpoint: str
    permission: str | None = None


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    display_name: str
    description: str
    feature_flag_key: str
    default_enabled: bool = True
    dependencies: tuple[str, ...] = ()
    blueprint_names: tuple[str, ...] = ()
    admin_nav_entries: tuple[NavEntry, ...] = ()
    pos_nav_entries: tuple[NavEntry, ...] = ()
    api_resources: tuple[str, ...] = ()
    required_roles: tuple[str, ...] = ("admin",)
    docs_location: str | None = None
    health_check: HealthCheck = field(default=_healthy, compare=False)


MODULES: dict[str, ModuleDefinition] = {
    "public_site": ModuleDefinition(
        key="public_site",
        display_name="Public Site",
        description="Marketing pages, gallery, custom order lead capture, and contact pages.",
        feature_flag_key="module.public_site.enabled",
        blueprint_names=("public",),
        required_roles=(),
        docs_location="DESIGN.md#public-website",
    ),
    "auth": ModuleDefinition(
        key="auth",
        display_name="Authentication",
        description="Login, logout, roles, and user session security.",
        feature_flag_key="module.auth.enabled",
        blueprint_names=("auth",),
        required_roles=(),
    ),
    "dashboard": ModuleDefinition(
        key="dashboard",
        display_name="Dashboard",
        description="Private operator dashboard and shared admin resource views.",
        feature_flag_key="module.dashboard.enabled",
        blueprint_names=("dashboard",),
        admin_nav_entries=(NavEntry("Dashboard", "dashboard.index"),),
    ),
    "products": ModuleDefinition(
        key="products",
        display_name="Products",
        description="Product Studio, categories, collections, and product license tracking.",
        feature_flag_key="module.products.enabled",
        blueprint_names=("products",),
        api_resources=("products", "categories", "collections"),
        admin_nav_entries=(NavEntry("Product Studio", "products.studio"),),
    ),
    "inventory": ModuleDefinition(
        key="inventory",
        display_name="Inventory",
        description="Finished goods, filament/materials, locations, movement history, and stock alerts.",
        feature_flag_key="module.inventory.enabled",
        dependencies=("products",),
        blueprint_names=("inventory",),
        api_resources=("inventory-records", "inventory-locations", "filament-spools"),
        admin_nav_entries=(NavEntry("Inventory", "inventory.list_resource"),),
        required_roles=("admin", "staff"),
    ),
    "printers": ModuleDefinition(
        key="printers",
        display_name="Printers",
        description="Printer fleet and AMS tracking.",
        feature_flag_key="module.printers.enabled",
        blueprint_names=("printers",),
        api_resources=("printers", "ams-units"),
        required_roles=("admin", "staff"),
    ),
    "print_jobs": ModuleDefinition(
        key="print_jobs",
        display_name="Print Jobs",
        description="Print queue, production status, and failure tracking.",
        feature_flag_key="module.print_jobs.enabled",
        dependencies=("products", "printers"),
        blueprint_names=("print_jobs",),
        api_resources=("print-jobs",),
        required_roles=("admin", "staff"),
    ),
    "customers": ModuleDefinition(
        key="customers",
        display_name="Customers",
        description="Customer records for orders, POS, and custom requests.",
        feature_flag_key="module.customers.enabled",
        blueprint_names=("customers",),
        api_resources=("customers",),
        required_roles=("admin", "staff"),
    ),
    "orders": ModuleDefinition(
        key="orders",
        display_name="Orders",
        description="Orders, items, payments, refunds, and fulfillment data.",
        feature_flag_key="module.orders.enabled",
        dependencies=("customers", "products"),
        blueprint_names=("orders",),
        api_resources=("orders", "order-items", "payments"),
        required_roles=("admin", "staff"),
    ),
    "custom_orders": ModuleDefinition(
        key="custom_orders",
        display_name="Custom Orders",
        description="Custom order requests, deposits, notes, and conversion workflow.",
        feature_flag_key="module.custom_orders.enabled",
        blueprint_names=("custom_orders",),
        api_resources=("custom-requests",),
        required_roles=("admin", "staff"),
    ),
    "promotion": ModuleDefinition(
        key="promotion",
        display_name="Promotion",
        description="Social content queue and market display sign generation.",
        feature_flag_key="module.promotion.enabled",
        dependencies=("products",),
        blueprint_names=("promotion",),
        api_resources=("content-drafts", "sign-assets"),
        admin_nav_entries=(
            NavEntry("Content Queue", "promotion.draft_list"),
            NavEntry("Display Signs", "promotion.sign_list"),
        ),
    ),
    "pos": ModuleDefinition(
        key="pos",
        display_name="POS",
        description="Mobile-friendly checkout, sessions, payments, receipts, and closeout.",
        feature_flag_key="module.pos.enabled",
        dependencies=("orders", "inventory", "customers"),
        blueprint_names=("pos",),
        api_resources=("pos-sessions", "pos-sales"),
        required_roles=("admin", "staff"),
    ),
    "booth_mode": ModuleDefinition(
        key="booth_mode",
        display_name="Booth Mode",
        description="Market-day command screen for break-even, payment mix, sales pace, and action hints.",
        feature_flag_key="module.booth_mode.enabled",
        dependencies=("pos", "markets", "inventory"),
        blueprint_names=("booth_mode",),
        admin_nav_entries=(NavEntry("Booth Mode", "booth_mode.index"),),
        required_roles=("admin", "staff"),
    ),
    "markets": ModuleDefinition(
        key="markets",
        display_name="Markets",
        description="Vendor markets, applications, packing lists, sales attribution, and performance.",
        feature_flag_key="module.markets.enabled",
        dependencies=("pos", "inventory"),
        blueprint_names=("markets",),
        api_resources=(
            "markets",
            "market-packing-lists",
            "market-tasks",
            "market-timeline-events",
            "market-weather-snapshots",
            "market-hotel-bookings",
            "market-documents",
        ),
    ),
    "receipts": ModuleDefinition(
        key="receipts",
        display_name="Receipts & Expenses",
        description="Receipt upload, extraction drafts, review, approval, and expense ledger creation.",
        feature_flag_key="module.receipts.enabled",
        blueprint_names=("receipts",),
        api_resources=("receipts", "receipt-line-items"),
    ),
    "expense_ledger": ModuleDefinition(
        key="expense_ledger",
        display_name="Expense Ledger",
        description="Structured ledger entries created manually or from approved receipts.",
        feature_flag_key="module.expense_ledger.enabled",
        dependencies=("receipts",),
        blueprint_names=("expenses",),
        api_resources=("expenses",),
    ),
    "trend_scout": ModuleDefinition(
        key="trend_scout",
        display_name="AI Trend Scout",
        description="Autonomous trend monitoring: scrapes marketplaces, communities, and social sources to detect rising product trends and business opportunities.",
        feature_flag_key="module.trend_scout.enabled",
        dependencies=(),
        blueprint_names=("trend_scout",),
        api_resources=("trend-reports", "trend-opportunity-scores", "trend-source-health"),
        admin_nav_entries=(NavEntry("Trend Scout", "trend_scout.index"),),
        docs_location="docs/AI Design Trend Scout Implementation.md",
    ),
    "dfp_intelligence": ModuleDefinition(
        key="dfp_intelligence",
        display_name="DFP Intelligence",
        description="Historical warehouse, Market Advisor, Ask DFP, and decision feedback loop.",
        feature_flag_key="module.dfp_intelligence.enabled",
        dependencies=("analytics", "markets", "inventory"),
        blueprint_names=("intelligence",),
        api_resources=("intelligence",),
        admin_nav_entries=(NavEntry("DFP Intelligence", "intelligence.index"),),
        docs_location="docs/DFPos Intelligence microservice.md",
    ),
    "analytics": ModuleDefinition(
        key="analytics",
        display_name="Analytics",
        description="Executive, product, market, inventory, print, expense, and POS analytics.",
        feature_flag_key="module.analytics.enabled",
        dependencies=("orders", "inventory", "markets", "expense_ledger"),
        blueprint_names=("analytics",),
        api_resources=("analytics",),
    ),
    "cost_engine": ModuleDefinition(
        key="cost_engine",
        display_name="Cost Engine",
        description="Reusable cost, price, margin, and profitability calculations.",
        feature_flag_key="module.cost_engine.enabled",
        dependencies=("products", "orders", "markets", "expense_ledger"),
        blueprint_names=("cost_engine",),
        api_resources=("cost-engine",),
    ),
    "prep_tasks": ModuleDefinition(
        key="prep_tasks",
        display_name="Prep Tasks",
        description="Reusable prep templates, generated market tasks, readiness scores, and packing guidance.",
        feature_flag_key="module.prep_tasks.enabled",
        dependencies=("markets", "inventory", "print_jobs"),
        blueprint_names=("prep_tasks",),
        api_resources=("prep-tasks", "prep-task-templates"),
        admin_nav_entries=(
            NavEntry("Prep Tasks", "prep_tasks.list_resource"),
            NavEntry("Follow-Up Queue", "prep_tasks.follow_up_queue"),
            NavEntry("Impulse Tray", "prep_tasks.impulse_tray_optimizer"),
        ),
    ),
    "table_layouts": ModuleDefinition(
        key="table_layouts",
        display_name="Table Layout Planner",
        description="Product placement grid with table sections, inventory allocation, and layout templates.",
        feature_flag_key="module.table_layouts.enabled",
        dependencies=("markets", "products"),
        blueprint_names=("table_layouts",),
        admin_nav_entries=(NavEntry("Table Layouts", "table_layouts.list_layouts"),),
    ),
    "api": ModuleDefinition(
        key="api",
        display_name="REST API",
        description="Token-authenticated API and OpenAPI documentation.",
        feature_flag_key="module.api.enabled",
        blueprint_names=("api",),
        required_roles=("admin", "api_only"),
    ),
    "settings": ModuleDefinition(
        key="settings",
        display_name="Settings",
        description="Application settings, themes, module status, and feature flags.",
        feature_flag_key="module.settings.enabled",
        blueprint_names=("settings", "api_tokens"),
        api_resources=("businesses",),
    ),
    "audit_logs": ModuleDefinition(
        key="audit_logs",
        display_name="Audit Logs",
        description="Audit-log microservice dispatch and admin visibility.",
        feature_flag_key="module.audit_logs.enabled",
        default_enabled=True,
        blueprint_names=("audit_logs",),
    ),
    "report_studio": ModuleDefinition(
        key="report_studio",
        display_name="Report Studio",
        description="Centralized reporting hub for markets, products, inventory, POS, orders, printers, and promotion.",
        feature_flag_key="module.report_studio.enabled",
        dependencies=(),
        blueprint_names=("report_studio",),
        api_resources=("report-studio",),
        admin_nav_entries=(NavEntry("Report Studio", "report_studio.home"),),
        docs_location="docs/New Ideas by Category.md#report-studio",
    ),
    "notifications": ModuleDefinition(
        key="notifications",
        display_name="Notifications",
        description="In-app notification alerts for trends, system events, and workflow milestones.",
        feature_flag_key="module.notifications.enabled",
        default_enabled=True,
        blueprint_names=("notifications",),
        admin_nav_entries=(NavEntry("Notifications", "notifications.notification_list"),),
    ),
    "feature_flags": ModuleDefinition(
        key="feature_flags",
        display_name="Feature Flags",
        description="Database and config-backed module enablement controls.",
        feature_flag_key="module.feature_flags.enabled",
        default_enabled=True,
        dependencies=("settings",),
        api_resources=("feature-flags",),
    ),
}


BLUEPRINT_TO_MODULE: dict[str, str] = {
    blueprint: module.key
    for module in MODULES.values()
    for blueprint in module.blueprint_names
}


API_RESOURCE_TO_MODULE: dict[str, str] = {
    resource: module.key
    for module in MODULES.values()
    for resource in module.api_resources
}


def get_module(key: str) -> ModuleDefinition | None:
    return MODULES.get(key)


def list_modules() -> list[ModuleDefinition]:
    return list(MODULES.values())


def is_feature_enabled(flag_key: str, default: bool = True) -> bool:
    env_key = "FEATURE_" + flag_key.upper().replace(".", "_").replace("-", "_")
    if env_key in current_app.config:
        return bool(current_app.config[env_key])

    try:
        record = db.session.query(FeatureFlag).filter_by(key=flag_key).first()
        if record is not None:
            return bool(record.enabled)

        setting = db.session.query(Setting).filter_by(key=flag_key).first()
        if setting is not None:
            return setting.value.strip().lower() in {"1", "true", "yes", "on"}
    except SQLAlchemyError:
        db.session.rollback()
    return default


def is_module_enabled(module_key: str) -> bool:
    module = MODULES[module_key]
    if not is_feature_enabled(module.feature_flag_key, module.default_enabled):
        return False
    return all(is_module_enabled(dep) for dep in module.dependencies)


def module_statuses() -> list[dict[str, object]]:
    statuses = []
    for module in list_modules():
        enabled = is_module_enabled(module.key)
        healthy, message = module.health_check()
        statuses.append(
            {
                "key": module.key,
                "display_name": module.display_name,
                "description": module.description,
                "feature_flag_key": module.feature_flag_key,
                "default_enabled": module.default_enabled,
                "enabled": enabled,
                "dependencies": module.dependencies,
                "health": "healthy" if healthy else "unhealthy",
                "health_message": message,
                "docs_location": module.docs_location,
            }
        )
    return statuses
