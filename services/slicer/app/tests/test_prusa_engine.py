from __future__ import annotations

import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.engines.base import EngineFailure, SliceOptions
from app.services.engines.prusa import PrusaEngine


class _Proc:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _options(printer: str = "bambu_a1", **overrides: object) -> SliceOptions:
    values: dict[str, object] = {
        "model_filename": "rainbow-dragon.stl",
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
        "filament_density": "1.24",
    }
    values.update(overrides)
    return SliceOptions.from_request(printer, values, preserve_orientation=False)


def _engine() -> PrusaEngine:
    profiles = Path(__file__).resolve().parents[2] / "slicer_profiles"
    return PrusaEngine("prusa-slicer", profiles)


def test_probe_reads_a_stable_prusaslicer_version(monkeypatch):
    def fake_run(command, **_kwargs):
        assert command == ["prusa-slicer", "--version"]
        return _Proc(stdout=b"PrusaSlicer 2.8.1+linux-x64\n")

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", fake_run)

    probe = _engine().probe()

    assert probe.available is True
    assert probe.engine_version == "2.8.1"


@pytest.mark.parametrize(
    ("printer", "profile_name"),
    [
        ("bambu_a1", "bambu_a1.ini"),
        ("bambu_p1p", "bambu_p1p.ini"),
        ("bambu_x1c", "bambu_x1c.ini"),
    ],
)
def test_slice_maps_supported_printers_to_existing_profiles(tmp_path, monkeypatch, printer, profile_name):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if "--export-gcode" in command:
            output = Path(command[command.index("--output") + 1])
            output.write_text(
                "; total filament used [g] = 5.00\n"
                "; estimated printing time (normal mode) = 10m\n"
                "; total layers count: 42\n",
                encoding="utf-8",
            )
        return _Proc(stdout=b"PrusaSlicer 2.8.1+linux-x64\n")

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", fake_run)

    artifact = _engine().slice(model_path, tmp_path / "workspace", _options(printer))

    assert not isinstance(artifact, EngineFailure)
    command = commands[-1]
    assert Path(command[command.index("--load") + 1]).name == profile_name
    assert artifact.profile_ids == {"printer": printer, "profile": profile_name}


@pytest.mark.parametrize("density", ["0.2", 20, "20%"])
def test_slice_normalizes_fill_density_and_returns_gcode_artifact(tmp_path, monkeypatch, density):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if "--export-gcode" in command:
            output = Path(command[command.index("--output") + 1])
            output.write_text(
                "; total filament used [g] = 5.00\n"
                "; estimated printing time (normal mode) = 1h 30m\n"
                "; total layers count: 42\n",
                encoding="utf-8",
            )
        return _Proc(stdout=b"PrusaSlicer 2.8.1+linux-x64\n")

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", fake_run)

    artifact = _engine().slice(model_path, tmp_path / "workspace", _options(infill_percent=density))

    assert not isinstance(artifact, EngineFailure)
    command = commands[-1]
    for flag in (
        "--layer-height",
        "--perimeters",
        "--top-solid-layers",
        "--bottom-solid-layers",
        "--fill-pattern",
        "--support-material",
        "--support-material-buildplate-only",
        "--brim-width",
        "--nozzle-diameter",
        "--fill-density",
        "--filament-density",
        "--filament-type",
    ):
        assert flag in command
    assert command[command.index("--fill-density") + 1] == "20%"
    assert artifact.artifact_path.parent == tmp_path / "workspace"
    assert artifact.artifact_path.suffix == ".gcode"
    assert artifact.filament_grams == Decimal("5.00")
    assert artifact.print_minutes == Decimal("90.0")
    assert artifact.layer_count == 42
    assert artifact.estimate_only is True
    assert artifact.direct_print_eligible is False


@pytest.mark.parametrize(
    ("fake_run", "expected_code"),
    [
        (lambda _command, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()), "executable_missing"),
        (
            lambda _command, **_kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("prusa-slicer", 600)),
            "timeout",
        ),
        (lambda _command, **_kwargs: _Proc(returncode=2, stderr=b"x" * 2048), "execution_failed"),
    ],
)
def test_slice_classifies_runtime_failures_as_fallback_eligible(tmp_path, monkeypatch, fake_run, expected_code):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")
    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", fake_run)

    failure = _engine().slice(model_path, tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == expected_code
    assert failure.fallback_eligible is True
    assert len(str(failure.diagnostics.get("stderr", ""))) <= 512


def test_slice_classifies_missing_output_and_required_estimates_as_fallback_eligible(tmp_path, monkeypatch):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", lambda _command, **_kwargs: _Proc())
    missing_output = _engine().slice(model_path, tmp_path / "workspace", _options())

    assert isinstance(missing_output, EngineFailure)
    assert missing_output.code == "missing_output"
    assert missing_output.fallback_eligible is True

    def writes_incomplete_gcode(command, **_kwargs):
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("; total filament used [g] = 5.00\n", encoding="utf-8")
        return _Proc()

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", writes_incomplete_gcode)
    missing_estimates = _engine().slice(model_path, tmp_path / "workspace", _options())

    assert isinstance(missing_estimates, EngineFailure)
    assert missing_estimates.code == "missing_stats"
    assert missing_estimates.fallback_eligible is True


def test_slice_classifies_malformed_numeric_gcode_stats_as_invalid_output(tmp_path, monkeypatch):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")

    def writes_malformed_gcode(command, **_kwargs):
        output = Path(command[command.index("--output") + 1])
        output.write_text(
            "; total filament used [g] = 5..00\n"
            "; estimated printing time (normal mode) = 10m\n",
            encoding="utf-8",
        )
        return _Proc()

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", writes_malformed_gcode)

    failure = _engine().slice(model_path, tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "invalid_output"
    assert failure.fallback_eligible is True


def test_slice_removes_stale_workspace_artifact_before_subprocess_runs(tmp_path, monkeypatch):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    stale_artifact = workspace / "model.gcode"
    stale_artifact.write_text(
        "; total filament used [g] = 99.00\n; estimated printing time (normal mode) = 9h\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", lambda _command, **_kwargs: _Proc())

    failure = _engine().slice(model_path, workspace, _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "missing_output"
    assert not stale_artifact.exists()
