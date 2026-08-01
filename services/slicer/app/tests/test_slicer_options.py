from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.services import slicer
from app.services.engines.stats import _normalize_fill_density


def test_normalize_fill_density_accepts_common_forms():
    assert _normalize_fill_density(20) == "20%"
    assert _normalize_fill_density("20%") == "20%"
    assert _normalize_fill_density("0.2") == "20%"
    assert _normalize_fill_density(Decimal("12.50")) == "12.5%"
    assert slicer._normalize_fill_density("0.2") == "20%"


def test_normalize_fill_density_clamps_out_of_range_values():
    assert _normalize_fill_density("-5") == "0%"
    assert _normalize_fill_density("500") == "100%"


def test_slice_model_passes_percent_fill_density_to_prusaslicer(tmp_path, monkeypatch):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")
    commands: list[list[str]] = []

    class Proc:
        returncode = 0
        stderr = b""
        stdout = b"PrusaSlicer 2.8.1"

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if "--export-gcode" in cmd:
            output_path = cmd[cmd.index("--output") + 1]
            with open(output_path, "w", encoding="utf-8") as gcode:
                gcode.write("; total filament used [g] = 5.00\n; estimated printing time (normal mode) = 10m\n")
        return Proc()

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", fake_run)

    result = slicer.slice_model(
        str(model_path),
        slicer_options={"infill_percent": "15%"},
    )

    assert result.success is True
    export_command = commands[1]
    assert export_command[export_command.index("--fill-density") + 1] == "15%"
    assert Path(export_command[export_command.index("--output") + 1]).parent == model_path.parent / "slice-output"
    assert result.gcode is not None
    assert "total filament used" in result.gcode


def test_slice_model_preserves_prusa_error_text_with_a_bounded_stderr_diagnostic(tmp_path, monkeypatch):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")

    class Proc:
        def __init__(self, returncode: int, stderr: bytes = b"") -> None:
            self.returncode = returncode
            self.stdout = b"PrusaSlicer 2.8.1+linux-x64\n"
            self.stderr = stderr

    def fake_run(command, **_kwargs):
        if "--version" in command:
            return Proc(0)
        return Proc(2, b"x" * 2048)

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", fake_run)

    result = slicer.slice_model(str(model_path))

    assert result.success is False
    assert result.error == f"PrusaSlicer exited with code 2. stderr: {'x' * 512}"


@pytest.mark.parametrize(
    ("profile_name", "slicer_options", "error"),
    [
        ("unknown-printer", {}, "The requested printer profile is unsupported."),
        ("", {}, "The requested printer profile is unsupported."),
        ("bambu_a1", {"nozzle_diameter": "0.6"}, "Only a 0.4 mm nozzle is supported."),
        ("bambu_a1", {"material": "NYLON"}, "The requested material is unsupported."),
        ("bambu_a1", {"material": ""}, "The requested material is unsupported."),
    ],
)
def test_slice_model_rejects_explicit_invalid_engine_options_before_probe(
    tmp_path, monkeypatch, profile_name, slicer_options, error
):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("invalid requests must not probe or execute PrusaSlicer")

    monkeypatch.setattr("app.services.engines.prusa.subprocess.run", should_not_run)

    result = slicer.slice_model(str(model_path), profile_name=profile_name, slicer_options=slicer_options)

    assert result.success is False
    assert result.error == error
