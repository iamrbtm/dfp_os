from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import Setting


DEFAULT_SETTINGS: dict[str, str] = {
    "store_name": "Dude Fish Printing",
    "store_tagline": "Bringing creativity to life, one layer at a time.",
    "store_email": "hello@dudefishprinting.com",
    "store_phone": "",
    "store_address": "",
    "store_city": "Clarksville",
    "store_state": "TN",
    "store_zip": "",
    "currency_symbol": "$",
    "tax_rate": "0.00",
    "pos_default_opening_cash": "50.00",
    "low_stock_threshold": "5",
    "default_theme": "dfp-github-light",
    "pos_card_processor": "placeholder",
    "pos_card_processing_enabled": "false",
    "cost_engine_cost_per_gram": "0.025",
    "cost_engine_labor_rate": "18.00",
    "cost_engine_packaging_cost": "0.50",
    "cost_engine_machine_hour_rate": "0.50",
    "cost_engine_energy_hour_rate": "0.18",
    "cost_engine_depreciation_hour_rate": "0.22",
    "cost_engine_maintenance_hour_rate": "0.06",
    "cost_engine_ams_waste_hour_rate": "0.04",
    "cost_engine_failure_rate": "0.05",
    "cost_engine_target_margin_percent": "55.00",
}


def get_setting(key: str, default: str = "") -> str:
    instance = db.session.scalar(select(Setting).where(Setting.key == key))
    if instance is None:
        return default
    return instance.value


def set_setting(key: str, value: str, description: str | None = None, type: str = "string") -> Setting:
    instance = db.session.scalar(select(Setting).where(Setting.key == key))
    if instance is None:
        instance = Setting(key=key, value=value, description=description, type=type)
        db.session.add(instance)
    else:
        instance.value = value
        if description is not None:
            instance.description = description
        instance.type = type
    db.session.commit()
    return instance


def get_all_settings() -> list[Setting]:
    return db.session.scalars(select(Setting).order_by(Setting.key)).all()


def get_setting_typed(key: str, default: str = "") -> str | bool | int | float | Decimal:
    instance = db.session.scalar(select(Setting).where(Setting.key == key))
    if instance is None:
        return default
    match instance.type:
        case "boolean":
            return instance.value.strip().lower() in {"1", "true", "yes", "on"}
        case "integer":
            try:
                return int(instance.value)
            except (ValueError, TypeError):
                return 0
        case "decimal":
            try:
                return Decimal(instance.value)
            except (ValueError, TypeError):
                return Decimal("0")
        case _:
            return instance.value


def seed_default_settings() -> int:
    count = 0
    for key, value in DEFAULT_SETTINGS.items():
        existing = db.session.scalar(select(Setting).where(Setting.key == key))
        if existing is None:
            db.session.add(Setting(key=key, value=value))
            count += 1
    if count:
        db.session.commit()
    return count
