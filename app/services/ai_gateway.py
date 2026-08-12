from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

KILO_GATEWAY_BASE_URL = "https://api.kilo.ai/api/gateway"


@dataclass(frozen=True)
class AIProviderSettings:
    provider: str
    api_key: str
    base_url: str | None


def configured_ai_provider() -> str:
    return str(current_app.config.get("AI_PROVIDER", "openai") or "openai").strip().lower()


def get_ai_provider_settings(provider: str | None = None) -> AIProviderSettings:
    selected = (provider or configured_ai_provider()).strip().lower()
    if selected == "kilo":
        return AIProviderSettings(
            provider="kilo",
            api_key=current_app.config.get("KILO_API_KEY", ""),
            base_url=current_app.config.get("KILO_GATEWAY_BASE_URL", KILO_GATEWAY_BASE_URL),
        )
    return AIProviderSettings(
        provider="openai",
        api_key=current_app.config.get("OPENAI_API_KEY", ""),
        base_url=current_app.config.get("OPENAI_BASE_URL") or None,
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
        return current_app.config.get(
            f"KILO_MODEL_{feature_key}",
            current_app.config.get("KILO_MODEL", "anthropic/claude-sonnet-4.5"),
        )
    return current_app.config.get(
        f"OPENAI_MODEL_{feature_key}",
        current_app.config.get("OPENAI_MODEL", "gpt-4o-mini"),
    )
