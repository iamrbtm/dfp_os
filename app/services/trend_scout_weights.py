from __future__ import annotations

import hashlib
import json
from typing import Any

from flask import has_app_context

from app.extensions import db
from app.models.setting import Setting


DEFAULT_SCORE_WEIGHTS: dict[str, float] = {
    "purchase_intent": 0.30,
    "trend_velocity": 0.18,
    "price_resilience": 0.14,
    "low_saturation": 0.12,
    "local_fit": 0.10,
    "production_fit": 0.12,
    "license_risk": 0.16,
}

DEFAULT_SOURCE_WEIGHTS: dict[str, float] = {
    "internal_demand": 1.6,
    "google_trends": 1.3,
    "etsy": 1.25,
    "last30days": 1.2,
    "makerworld": 1.15,
    "tiktok": 1.15,
    "printables": 1.1,
    "myminifactory": 1.0,
    "reddit": 0.95,
    "pinterest": 0.9,
    "bgg": 0.8,
}

DEFAULT_BUYER_SOURCE_WEIGHTS: dict[str, float] = {
    "internal_demand": 1.0,
    "etsy": 0.65,
    "google_trends": 0.35,
    "tiktok": 0.25,
    "last30days": 0.20,
    "reddit": 0.15,
    "pinterest": 0.15,
}

DEFAULT_METRIC_WEIGHTS: dict[str, float] = {
    "downloads": 0.22,
    "download_count": 0.22,
    "prints_count": 0.2,
    "print_count": 0.2,
    "makes": 0.2,
    "likes": 0.15,
    "num_favorers": 0.15,
    "favorites": 0.15,
    "saves": 0.14,
    "views": 0.08,
    "visits": 0.08,
    "impressions": 0.05,
    "comments": 0.08,
    "shares": 0.1,
    "interest": 0.05,
    "event_count": 0.35,
    "quantity": 0.45,
    "purchase_score": 0.6,
    "revenue": 0.08,
}

PREFIX_SCORE = "trend_weight."
PREFIX_SOURCE = "trend_source."
PREFIX_BUYER = "trend_buyer."
PREFIX_METRIC = "trend_metric."
PREFIX_SOURCE_ENABLED = "trend_source_enabled."


def _weights_from_settings(prefix: str, defaults: dict[str, float]) -> dict[str, float]:
    if not has_app_context():
        return dict(defaults)

    out = {}
    for key in defaults:
        setting = db.session.query(Setting).filter(
            Setting.key == prefix + key
        ).first()
        if setting and setting.value:
            try:
                out[key] = float(setting.value)
            except (ValueError, TypeError):
                out[key] = defaults[key]
        else:
            out[key] = defaults[key]
    return out


def load_score_weights() -> dict[str, float]:
    return _weights_from_settings(PREFIX_SCORE, DEFAULT_SCORE_WEIGHTS)


def load_source_weights() -> dict[str, float]:
    return _weights_from_settings(PREFIX_SOURCE, DEFAULT_SOURCE_WEIGHTS)


def load_buyer_source_weights() -> dict[str, float]:
    return _weights_from_settings(PREFIX_BUYER, DEFAULT_BUYER_SOURCE_WEIGHTS)


def load_metric_weights() -> dict[str, float]:
    return _weights_from_settings(PREFIX_METRIC, DEFAULT_METRIC_WEIGHTS)


def load_all_weights() -> dict[str, Any]:
    return {
        "score_weights": load_score_weights(),
        "source_weights": load_source_weights(),
        "buyer_source_weights": load_buyer_source_weights(),
        "metric_weights": load_metric_weights(),
    }


def load_source_enabled_state(source_keys: list[str] | tuple[str, ...] | set[str]) -> dict[str, bool]:
    if not has_app_context():
        return {key: True for key in source_keys}

    state = {}
    for key in source_keys:
        setting = db.session.query(Setting).filter(
            Setting.key == PREFIX_SOURCE_ENABLED + key
        ).first()
        state[key] = setting is None or setting.value == "1"
    return state


def scoring_version() -> str:
    all_w = load_all_weights()
    raw = json.dumps(all_w, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def save_weight(prefix: str, key: str, value: float) -> None:
    setting_key = prefix + key
    setting = db.session.query(Setting).filter(
        Setting.key == setting_key
    ).first()
    if setting:
        setting.value = str(value)
    else:
        setting = Setting(
            key=setting_key,
            value=str(value),
            description=f"Trend Scout {prefix.strip('.')} weight: {key}",
            type="float",
        )
        db.session.add(setting)
    db.session.commit()


def validate_score_weights(weights: dict[str, float]) -> list[str]:
    errors = []
    required = set(DEFAULT_SCORE_WEIGHTS)
    provided = set(weights)
    missing = required - provided
    if missing:
        errors.append(f"Missing weights: {', '.join(sorted(missing))}")

    extra = provided - required
    if extra:
        errors.append(f"Unknown weights: {', '.join(sorted(extra))}")

    for key, val in weights.items():
        try:
            val = float(val)
        except (TypeError, ValueError):
            errors.append(f"'{key}' is not a valid number")
            continue
        if val < -1.0 or val > 2.0:
            errors.append(f"'{key}' ({val}) is outside allowed range [-1.0, 2.0]")

    return errors


def seed_default_weights() -> list[str]:
    created = []
    for prefix, defaults in [
        (PREFIX_SCORE, DEFAULT_SCORE_WEIGHTS),
        (PREFIX_SOURCE, DEFAULT_SOURCE_WEIGHTS),
        (PREFIX_BUYER, DEFAULT_BUYER_SOURCE_WEIGHTS),
        (PREFIX_METRIC, DEFAULT_METRIC_WEIGHTS),
    ]:
        for key, default_val in defaults.items():
            setting_key = prefix + key
            existing = db.session.query(Setting).filter(
                Setting.key == setting_key
            ).first()
            if not existing:
                label = prefix.replace("trend_", "").replace(".", " ").strip()
                db.session.add(Setting(
                    key=setting_key,
                    value=str(default_val),
                    description=f"Trend Scout {label} weight: {key}",
                    setting_type="float",
                ))
                created.append(setting_key)
    if created:
        db.session.commit()
    return created
