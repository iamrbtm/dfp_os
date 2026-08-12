from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

from app.services.settings import get_setting

KILO_GATEWAY_BASE_URL = "https://api.kilo.ai/api/gateway"


@dataclass(frozen=True)
class AIProviderSettings:
    provider: str
    api_key: str
    base_url: str | None


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
