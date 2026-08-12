from __future__ import annotations

from app.services.ai_gateway import get_ai_provider_settings, model_for
from app.services.settings import set_setting


def test_ai_gateway_defaults_to_openai(app):
    with app.app_context():
        app.config["AI_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = "openai-key"
        app.config["OPENAI_MODEL_MARKET_CATALOG"] = "gpt-market"

        settings = get_ai_provider_settings()

        assert settings.provider == "openai"
        assert settings.api_key == "openai-key"
        assert settings.base_url is None
        assert model_for("market_catalog") == "gpt-market"


def test_ai_gateway_supports_kilo_provider(app):
    with app.app_context():
        app.config["AI_PROVIDER"] = "kilo"
        app.config["KILO_API_KEY"] = "kilo-key"
        app.config["KILO_GATEWAY_BASE_URL"] = "https://api.kilo.ai/api/gateway"
        app.config["KILO_MODEL_MARKET_CATALOG"] = "anthropic/claude-sonnet-4.5"

        settings = get_ai_provider_settings()

        assert settings.provider == "kilo"
        assert settings.api_key == "kilo-key"
        assert settings.base_url == "https://api.kilo.ai/api/gateway"
        assert model_for("market_catalog") == "anthropic/claude-sonnet-4.5"


def test_ai_gateway_uses_database_settings_over_env(app):
    with app.app_context():
        app.config["AI_PROVIDER"] = "openai"
        app.config["OPENAI_API_KEY"] = "openai-key"
        set_setting("ai_provider", "kilo")
        set_setting("kilo_api_key", "db-kilo-key")
        set_setting("kilo_model_market_catalog", "anthropic/claude-opus-4.1")

        settings = get_ai_provider_settings()

        assert settings.provider == "kilo"
        assert settings.api_key == "db-kilo-key"
        assert model_for("market_catalog") == "anthropic/claude-opus-4.1"
