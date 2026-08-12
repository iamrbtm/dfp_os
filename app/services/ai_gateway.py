from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import current_app
import requests

from app.services.settings import get_setting

KILO_GATEWAY_BASE_URL = "https://api.kilo.ai/api/gateway"
_KILO_MODELS_CACHE: tuple[datetime, list["KiloModelOption"]] | None = None
_KILO_MODELS_CACHE_TTL = timedelta(hours=6)


@dataclass(frozen=True)
class AIProviderSettings:
    provider: str
    api_key: str
    base_url: str | None


@dataclass(frozen=True)
class KiloModelOption:
    id: str
    name: str
    is_free: bool


def configured_ai_provider() -> str:
    return _setting_or_config("AI_PROVIDER", "openai").strip().lower()


def get_ai_provider_settings(provider: str | None = None) -> AIProviderSettings:
    selected = (provider or configured_ai_provider()).strip().lower()
    if selected == "kilo":
        return AIProviderSettings(
            provider="kilo",
            api_key=_setting_or_config("KILO_API_KEY", ""),
            base_url=_setting_or_config("KILO_GATEWAY_BASE_URL", KILO_GATEWAY_BASE_URL),
        )
    return AIProviderSettings(
        provider="openai",
        api_key=_setting_or_config("OPENAI_API_KEY", ""),
        base_url=_setting_or_config("OPENAI_BASE_URL", "") or None,
    )


def ai_provider_configured(provider: str | None = None) -> bool:
    return bool(get_ai_provider_settings(provider).api_key)


def get_openai_compatible_client(provider: str | None = None):
    from openai import OpenAI

    settings = get_ai_provider_settings(provider)
    if not settings.api_key:
        raise RuntimeError(f"{settings.provider} API key is not configured.")
    kwargs = {"api_key": settings.api_key}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return OpenAI(**kwargs)


def model_for(feature: str) -> str:
    provider = configured_ai_provider()
    feature_key = feature.upper()
    if provider == "kilo":
        return _setting_or_config(
            f"KILO_MODEL_{feature_key}",
            _setting_or_config("KILO_MODEL", "anthropic/claude-sonnet-4.5"),
        )
    return _setting_or_config(
        f"OPENAI_MODEL_{feature_key}",
        _setting_or_config("OPENAI_MODEL", "gpt-4o-mini"),
    )


def _setting_or_config(key: str, default: str = "") -> str:
    env_value = current_app.config.get(key, default)
    value = get_setting(key.lower(), str(env_value or default))
    return str(value or "")


def list_kilo_model_options(timeout: int = 8) -> list[KiloModelOption]:
    global _KILO_MODELS_CACHE

    now = datetime.now(timezone.utc)
    if _KILO_MODELS_CACHE and now - _KILO_MODELS_CACHE[0] < _KILO_MODELS_CACHE_TTL:
        return _KILO_MODELS_CACHE[1]

    base_url = _setting_or_config("KILO_GATEWAY_BASE_URL", KILO_GATEWAY_BASE_URL).rstrip("/")
    try:
        response = requests.get(f"{base_url}/models", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        current_app.logger.warning("Kilo model list fetch failed: %s", exc)
        return _KILO_MODELS_CACHE[1] if _KILO_MODELS_CACHE else []

    options = []
    for item in payload.get("data", []):
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        options.append(
            KiloModelOption(
                id=model_id,
                name=str(item.get("name") or model_id).strip(),
                is_free=_is_free_model(item.get("pricing") or {}),
            )
        )
    sorted_options = sorted(
        options, key=lambda option: (not option.is_free, option.name.lower(), option.id)
    )
    _KILO_MODELS_CACHE = (now, sorted_options)
    return sorted_options


def _is_free_model(pricing: dict) -> bool:
    prompt = _decimal_or_none(pricing.get("prompt"))
    completion = _decimal_or_none(pricing.get("completion"))
    if prompt is None or completion is None:
        return False
    return prompt == 0 and completion == 0


def _decimal_or_none(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except InvalidOperation, TypeError, ValueError:
        return None
