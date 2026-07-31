from __future__ import annotations

from decimal import Decimal

from app.services import slicer


def test_normalize_fill_density_accepts_common_forms():
    assert slicer._normalize_fill_density(20) == "20%"
    assert slicer._normalize_fill_density("20%") == "20%"
    assert slicer._normalize_fill_density("0.2") == "20%"
    assert slicer._normalize_fill_density(Decimal("12.50")) == "12.5%"


def test_normalize_fill_density_clamps_out_of_range_values():
    assert slicer._normalize_fill_density("-5") == "0%"
    assert slicer._normalize_fill_density("500") == "100%"


def test_slice_model_passes_percent_fill_density_to_prusaslicer(tmp_path, monkeypatch):
    model_path = tmp_path / "model.stl"
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")
    commands: list[list[str]] = []

    class Proc:
        returncode = 0
        stderr = b""

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if "--export-gcode" in cmd:
            output_path = cmd[cmd.index("--output") + 1]
            with open(output_path, "w", encoding="utf-8") as gcode:
                gcode.write("; total filament used [g] = 5.00\n; estimated printing time (normal mode) = 10m\n")
        return Proc()

    monkeypatch.setattr(slicer.subprocess, "run", fake_run)

    result = slicer.slice_model(
        str(model_path),
        slicer_options={"infill_percent": "15%"},
    )

    assert result.success is True
    export_command = commands[1]
    assert export_command[export_command.index("--fill-density") + 1] == "15%"
    assert result.gcode is not None
    assert "total filament used" in result.gcode
