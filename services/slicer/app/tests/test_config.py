from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "internal_api_token": "test-slicer-token-0123456789abcdef",
        "engine_order": "bambu,prusa",
        "bambu_studio_path": "/opt/bambu-studio/AppRun",
        "bambu_profile_root": "/opt/bambu-studio/resources/profiles/BBL",
        "prusa_slicer_path": "prusa-slicer",
        "slice_timeout_seconds": 600,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "too-short",
        "change-me-slicer-token",
        "change-me-to-a-real-secret-token",
        "change_me_to_a_real_secret_token",
        "replace-with-a-random-32-byte-token",
        "replace_with_a_random_32_byte_token",
        "valid-looking-token-with-a-control\x00",
        "válid-looking-but-non-ascii-token-1234",
    ],
)
def test_startup_rejects_unsafe_internal_api_tokens(token: str):
    with pytest.raises(ValueError, match="SLICER_INTERNAL_API_TOKEN"):
        _settings(internal_api_token=token).validate_for_startup()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("engine_order", "prusa,bambu"),
        ("engine_order", "bambu,prusa,other"),
        ("bambu_studio_path", "relative/AppRun"),
        ("bambu_profile_root", "relative/profiles"),
        ("prusa_slicer_path", "  "),
        ("prusa_slicer_path", "prusa\x00slicer"),
    ],
)
def test_startup_rejects_invalid_engine_order_and_path_strings(field: str, value: str):
    with pytest.raises(ValueError):
        _settings(**{field: value}).validate_for_startup()


def test_valid_startup_configuration_is_accepted():
    configured = _settings()

    configured.validate_for_startup()

    assert Path(configured.bambu_studio_path).is_absolute()
    assert Path(configured.bambu_profile_root).is_absolute()


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (2, (1, 1)),
        (3, (2, 1)),
        (600, (300, 300)),
        (601, (301, 300)),
    ],
)
def test_total_slice_timeout_is_split_without_exceeding_budget(total: int, expected: tuple[int, int]):
    from app.api.dependencies import split_engine_timeouts

    budgets = split_engine_timeouts(total)

    assert budgets == expected
    assert sum(budgets) == total
    assert min(budgets) >= 1


def test_runtime_factory_wires_split_timeouts_to_exact_two_engines(monkeypatch: pytest.MonkeyPatch):
    from app.api import dependencies

    captured: dict[str, tuple[object, ...] | dict[str, object]] = {}

    class FakeResolver:
        def __init__(self, profile_root: Path) -> None:
            captured["profile_root"] = (profile_root,)

    class FakeEngine:
        def probe(self):
            return None

        def slice(self, *_args):
            return None

    def bambu_factory(executable, resolver, **kwargs):
        captured["bambu"] = {"executable": executable, "resolver": resolver, **kwargs}
        return FakeEngine()

    def prusa_factory(executable, profiles_dir, **kwargs):
        captured["prusa"] = {"executable": executable, "profiles_dir": profiles_dir, **kwargs}
        return FakeEngine()

    monkeypatch.setattr(dependencies, "BambuProfileResolver", FakeResolver)
    monkeypatch.setattr(dependencies, "BambuEngine", bambu_factory)
    monkeypatch.setattr(dependencies, "PrusaEngine", prusa_factory)
    monkeypatch.setattr(dependencies.settings, "slice_timeout_seconds", 5)
    dependencies.build_slicer_runtime.cache_clear()

    try:
        dependencies.build_slicer_runtime()
    finally:
        dependencies.build_slicer_runtime.cache_clear()

    assert captured["bambu"]["timeout"] == 3
    assert captured["prusa"]["timeout"] == 2
    assert captured["bambu"]["timeout"] + captured["prusa"]["timeout"] == 5


async def test_lifespan_validates_configuration_and_constructs_cached_runtime(monkeypatch: pytest.MonkeyPatch):
    import app.main as main_module

    calls: list[str] = []

    class Jobs:
        async def shutdown(self):
            calls.append("drained")

    class Cleanup:
        async def shutdown(self):
            calls.append("cleaned")

    class Runtime:
        jobs = Jobs()
        cleanup = Cleanup()

    runtime = Runtime()
    monkeypatch.setattr(
        type(main_module.settings),
        "validate_for_startup",
        lambda _self: calls.append("validated"),
    )
    monkeypatch.setattr(main_module, "build_slicer_runtime", lambda: calls.append("built") or runtime)
    app = main_module.create_app()

    async with app.router.lifespan_context(app):
        assert app.state.slicer_runtime is runtime

    assert calls == ["validated", "built", "drained", "cleaned"]


async def test_lifespan_rejects_bad_configuration_before_runtime_construction(monkeypatch: pytest.MonkeyPatch):
    import app.main as main_module

    built = False

    def fail_validation():
        raise ValueError("bad slicer config")

    def build_runtime():
        nonlocal built
        built = True

    monkeypatch.setattr(type(main_module.settings), "validate_for_startup", lambda _self: fail_validation())
    monkeypatch.setattr(main_module, "build_slicer_runtime", build_runtime)
    app = main_module.create_app()

    with pytest.raises(ValueError, match="bad slicer config"):
        async with app.router.lifespan_context(app):
            pass

    assert built is False


async def test_lifespan_cleanup_shutdown_runs_when_job_shutdown_raises(monkeypatch: pytest.MonkeyPatch):
    import app.main as main_module

    calls: list[str] = []

    class Jobs:
        async def shutdown(self):
            calls.append("jobs_failed")
            raise RuntimeError("job shutdown failed")

    class Cleanup:
        async def shutdown(self):
            calls.append("cleanup_drained")

    class Runtime:
        jobs = Jobs()
        cleanup = Cleanup()

    monkeypatch.setattr(type(main_module.settings), "validate_for_startup", lambda _self: None)
    monkeypatch.setattr(main_module, "build_slicer_runtime", Runtime)
    app = main_module.create_app()

    with pytest.raises(RuntimeError, match="job shutdown failed"):
        async with app.router.lifespan_context(app):
            pass

    assert calls == ["jobs_failed", "cleanup_drained"]
