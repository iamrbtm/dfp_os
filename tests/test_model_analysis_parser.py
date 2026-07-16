from decimal import Decimal
import json
import zipfile

from app.services.model_analysis import (
    _parse_gcode_stats,
    _parse_time_string,
    extract_3mf_slicer_settings,
)


def test_gcode_parser_finds_stats_before_long_configuration_footer(tmp_path):
    path = tmp_path / "quote.gcode"
    footer = "\n".join(f"; setting_{index} = value" for index in range(900))
    path.write_text(
        "; total filament used [g] = 56.58\n"
        "; estimated printing time (normal mode) = 1d 2h 3m 30s\n"
        "; total layers count: 422\n"
        f"{footer}\n",
        encoding="utf-8",
    )

    result = _parse_gcode_stats(path)

    assert result == {
        "filament_grams": Decimal("56.58"),
        "print_minutes": Decimal("1563.5"),
        "layer_count": 422,
    }


def test_gcode_parser_uses_selected_material_density_for_volume_fallback(tmp_path):
    path = tmp_path / "quote.gcode"
    path.write_text(
        "; filament used [cm3] = 10.00\n"
        "; estimated print time = 10m\n",
        encoding="utf-8",
    )

    result = _parse_gcode_stats(path, density=Decimal("1.27"))

    assert result["filament_grams"] == Decimal("12.70")


def test_time_parser_supports_days():
    assert _parse_time_string("2d 1h 5m") == 2945


def test_3mf_embedded_project_settings_are_detected(tmp_path):
    path = tmp_path / "project.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Metadata/project_settings.config",
            json.dumps({"layer_height": "0.16", "fill_density": "15%", "filament_type": ["PETG"]}),
        )

    settings = extract_3mf_slicer_settings(path)

    assert settings["layer_height"] == "0.16"
    assert settings["fill_density"] == "15%"
    assert settings["filament_type"] == ["PETG"]
