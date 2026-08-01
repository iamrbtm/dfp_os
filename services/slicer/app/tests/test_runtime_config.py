from __future__ import annotations

import pytest

from app.config import Settings


def _settings(**overrides: object) -> Settings:
    values = {
        "internal_api_token": "abcdefghijklmnopqrstuvwxyz123456",
    }
    values.update(overrides)
    return Settings(**values)


def test_runtime_defaults_target_pinned_bambu_primary_stack():
    settings = _settings()

    assert settings.bambu_studio_path == "/opt/bambu-studio/AppRun"
    assert settings.bambu_profile_root == "/opt/bambu-studio/resources/profiles/BBL"
    assert settings.prusa_slicer_path == "prusa-slicer"
    assert settings.engine_order == "bambu,prusa"
    assert settings.slice_timeout_seconds == 600
    assert settings.metadata_header_max_bytes == 6144
    assert settings.max_model_bytes == 268435456
    settings.validate_for_startup()


@pytest.mark.parametrize("field", ["bambu_studio_path", "bambu_profile_root"])
def test_runtime_rejects_relative_bambu_paths(field: str):
    settings = _settings(**{field: "relative/path"})

    with pytest.raises(ValueError, match=field.upper()):
        settings.validate_for_startup()


def test_runtime_requires_bambu_prusa_engine_order():
    settings = _settings(engine_order="prusa,bambu")

    with pytest.raises(ValueError, match="SLICER_ENGINE_ORDER"):
        settings.validate_for_startup()
