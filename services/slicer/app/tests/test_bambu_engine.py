from __future__ import annotations

import hashlib
import subprocess
import zipfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.engines.bambu import BambuEngine
from app.services.engines.bambu_profiles import ResolvedBambuProfiles
from app.services.engines.base import EngineFailure, RequestValidationError, SliceOptions


VALID_GCODE = (
    "; total filament used [g] = 6.25\n; estimated printing time (normal mode) = 1h 2m\n; total layers count: 123\n"
)


class _Proc:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Resolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Path]] = []

    def resolve(self, printer: str, material: str, workspace: Path) -> ResolvedBambuProfiles:
        workspace = Path(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        self.calls.append((printer, material, workspace))
        paths = [workspace / name for name in ("machine.json", "process.json", "filament.json")]
        for path in paths:
            path.write_text("{}\n", encoding="utf-8")
        return ResolvedBambuProfiles(
            machine_path=paths[0],
            process_path=paths[1],
            filament_path=paths[2],
            profile_ids={"machine": "A1", "process": "Standard", "filament": "Generic PLA"},
        )


def _options(filename: str = "rainbow dragon.stl", **overrides: object) -> SliceOptions:
    values: dict[str, object] = {
        "model_filename": filename,
        "nozzle_diameter": "0.4",
        "material": "PLA",
        "layer_height": "0.16",
        "perimeters": 3,
        "top_solid_layers": 4,
        "bottom_solid_layers": 5,
        "infill_percent": "0.2",
        "infill_pattern": "gyroid",
        "supports": "build_plate",
        "brim_width": "4",
    }
    values.update(overrides)
    return SliceOptions.from_request("bambu_a1", values, preserve_orientation=False)


def _model(tmp_path: Path, filename: str = "rainbow dragon.stl") -> Path:
    path = tmp_path / filename
    path.write_bytes((Path(__file__).parent / "fixtures/cube.stl").read_bytes())
    return path


def _artifact_path(command: list[str]) -> Path:
    return Path(command[command.index("--export-3mf") + 1])


def _write_artifact(command: list[str], gcode: str = VALID_GCODE, member: str = "Metadata/plate_1.gcode") -> Path:
    output = _artifact_path(command)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, gcode)
    return output


def test_probe_uses_apprun_help_without_a_shell_and_normalizes_the_pinned_version(monkeypatch):
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return _Proc(stdout=b"BambuStudio-02.07.01.62\n")

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", fake_run)

    probe = BambuEngine("/opt/bambu-studio/AppRun", _Resolver()).probe()

    assert probe.available is True
    assert probe.engine_version == "2.7.1.62"
    assert calls[0][0] == ["/opt/bambu-studio/AppRun", "--help"]
    assert calls[0][1]["shell"] is False


def test_slice_builds_safe_argument_array_and_returns_valid_native_artifact(tmp_path, monkeypatch):
    resolver = _Resolver()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        _write_artifact(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", fake_run)
    model_path = _model(tmp_path)
    workspace = tmp_path / "request-workspace"

    artifact = BambuEngine("/opt/bambu-studio/AppRun", resolver).slice(model_path, workspace, _options())

    assert not isinstance(artifact, EngineFailure)
    command, kwargs = calls[0]
    assert isinstance(command, list)
    assert kwargs["shell"] is False
    assert command[0] == "/opt/bambu-studio/AppRun"
    settings = command[command.index("--load-settings") + 1].split(";")
    assert [Path(value).name for value in settings] == ["machine.json", "process.json"]
    assert Path(command[command.index("--load-filaments") + 1]).name == "filament.json"
    assert command[command.index("--arrange") + 1] == "1"
    assert command[command.index("--slice") + 1] == "0"
    assert "--orient" in command
    for expected in (
        "--layer-height=0.16",
        "--wall-loops=3",
        "--top-shell-layers=4",
        "--bottom-shell-layers=5",
        "--sparse-infill-density=20%",
        "--sparse-infill-pattern=gyroid",
        "--enable-support=1",
        "--support-on-build-plate-only=1",
        "--brim-width=4",
    ):
        assert expected in command
    assert artifact.artifact_filename == "rainbow-dragon.gcode.3mf"
    assert artifact.artifact_media_type == "application/vnd.bambulab.gcode-3mf"
    assert artifact.artifact_size == artifact.artifact_path.stat().st_size
    assert artifact.artifact_sha256 == hashlib.sha256(artifact.artifact_path.read_bytes()).hexdigest()
    assert artifact.filament_grams == Decimal("6.25")
    assert artifact.print_minutes == Decimal("62.0")
    assert artifact.layer_count == 123
    assert artifact.profile_ids == {"machine": "A1", "process": "Standard", "filament": "Generic PLA"}
    assert artifact.direct_print_eligible is True
    assert artifact.estimate_only is False
    assert resolver.calls == [("bambu_a1", "PLA", workspace)]


def test_slice_preserves_uploaded_orientation_when_requested(tmp_path, monkeypatch):
    def fake_run(command, **_kwargs):
        _write_artifact(command)
        assert "--orient" not in command
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", fake_run)
    options = replace(_options(), preserve_orientation=True)

    artifact = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", options)

    assert not isinstance(artifact, EngineFailure)


@pytest.mark.parametrize(
    ("supports", "expected", "unexpected"),
    [
        ("none", {"--enable-support=0"}, {"--support-on-build-plate-only=0", "--support-on-build-plate-only=1"}),
        ("everywhere", {"--enable-support=1", "--support-on-build-plate-only=0"}, set()),
        ("build_plate", {"--enable-support=1", "--support-on-build-plate-only=1"}, set()),
    ],
)
def test_slice_maps_each_support_mode(tmp_path, monkeypatch, supports, expected, unexpected):
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        _write_artifact(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", fake_run)

    artifact = BambuEngine("AppRun", _Resolver()).slice(
        _model(tmp_path), tmp_path / "workspace", _options(supports=supports)
    )

    assert not isinstance(artifact, EngineFailure)
    assert expected <= set(commands[0])
    assert set(commands[0]).isdisjoint(unexpected)


@pytest.mark.parametrize(
    ("runner", "expected_code"),
    [
        (lambda _command, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()), "executable_missing"),
        (
            lambda _command, **_kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("AppRun", 37)),
            "timeout",
        ),
        (lambda _command, **_kwargs: (_ for _ in ()).throw(OSError("crash in /private/workspace")), "execution_failed"),
        (
            lambda _command, **_kwargs: _Proc(returncode=9, stderr=b"/private/workspace\n" + b"x" * 1024),
            "execution_failed",
        ),
    ],
)
def test_slice_classifies_runtime_failures_with_bounded_path_free_diagnostics(
    tmp_path, monkeypatch, runner, expected_code
):
    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", runner)

    failure = BambuEngine("AppRun", _Resolver(), timeout=37).slice(
        _model(tmp_path), tmp_path / "private-workspace", _options()
    )

    assert isinstance(failure, EngineFailure)
    assert failure.code == expected_code
    assert failure.fallback_eligible is True
    public_text = f"{failure.message} {failure.diagnostics}"
    assert len(str(failure.diagnostics.get("stderr", ""))) <= 512
    assert str(tmp_path) not in public_text
    assert "/private/workspace" not in public_text


@pytest.mark.parametrize(
    ("writer", "expected_code"),
    [
        (lambda _command: None, "missing_output"),
        (lambda command: _artifact_path(command).write_bytes(b"not a zip"), "invalid_output"),
        (lambda command: _write_artifact(command, member="Metadata/readme.txt"), "missing_gcode"),
        (lambda command: _write_artifact(command, gcode="; total filament used [g] = 6.25\n"), "missing_stats"),
    ],
)
def test_slice_rejects_missing_or_invalid_native_artifacts(tmp_path, monkeypatch, writer, expected_code):
    def fake_run(command, **_kwargs):
        writer(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", fake_run)

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == expected_code
    assert failure.fallback_eligible is True


def test_slice_removes_a_stale_artifact_before_running(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    stale = workspace / "rainbow-dragon.gcode.3mf"
    _write_artifact(["--export-3mf", str(stale)])
    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", lambda _command, **_kwargs: _Proc())

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), workspace, _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "missing_output"
    assert not stale.exists()


@pytest.mark.parametrize(
    ("changed", "expected_code"),
    [
        ({"printer": "../../other"}, "unsupported_printer"),
        ({"nozzle_diameter": Decimal("0.6")}, "unsupported_nozzle"),
        ({"material": "NYLON"}, "unsupported_material"),
        ({"model_suffix": ".exe"}, "unsupported_model_suffix"),
    ],
)
def test_slice_keeps_forged_request_values_terminal(tmp_path, monkeypatch, changed, expected_code):
    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("terminal input must not execute Bambu Studio"),
    )
    options = replace(_options(), **changed)

    with pytest.raises(RequestValidationError) as error:
        BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", options)

    assert error.value.code == expected_code
    assert error.value.fallback_eligible is False


def test_slice_rejects_an_unsafe_actual_model_extension_even_if_options_are_forged(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("unsafe input must not execute Bambu Studio"),
    )
    unsafe_model = _model(tmp_path, "payload.exe")

    with pytest.raises(RequestValidationError) as error:
        BambuEngine("AppRun", _Resolver()).slice(unsafe_model, tmp_path / "workspace", _options())

    assert error.value.code == "unsupported_model_suffix"


@pytest.mark.parametrize(
    ("filename", "embedded"),
    [("model.stl", True), ("model.obj", True), ("model.3mf", False)],
)
def test_slice_rejects_multicolor_without_an_embedded_3mf_recipe(tmp_path, monkeypatch, filename, embedded):
    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("unsupported multicolor must not execute Bambu Studio"),
    )
    options = _options(filename, multicolor=True, use_embedded_settings=embedded)

    with pytest.raises(RequestValidationError) as error:
        BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path, filename), tmp_path / "workspace", options)

    assert error.value.code == "unsupported_multicolor"
    assert error.value.fallback_eligible is False


def test_slice_allows_multicolor_only_for_3mf_with_embedded_settings_without_color_assignment(tmp_path, monkeypatch):
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        _write_artifact(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", fake_run)
    options = _options("model.3mf", multicolor=True, use_embedded_settings=True)

    artifact = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path, "model.3mf"), tmp_path / "workspace", options)

    assert not isinstance(artifact, EngineFailure)
    assert not any(argument.startswith("--") and "color" in argument.lower() for argument in commands[0])
