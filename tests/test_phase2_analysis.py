"""Phase 2 — model upload & analysis core (Issues 5, 8, 10, 11, 12, 23, 29, 32, 37).

These tests exercise the service-layer logic added in Phase 2. trimesh and
PrusaSlicer are optional on the host; tests that need them skip when they are
unavailable. The pure-Python helpers (materials, gcode parsing, task envelope,
quotable formats, slicer profile resolution, runtime checks) always run.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest

from app.services.materials import (
    MATERIAL_DEFAULTS,
    material_default_temp,
    resolve_density,
)
from app.services.model_analysis import (
    PREVIEW_ONLY_FORMATS,
    QUOTABLE_FORMATS,
    _parse_gcode_stats,
    _parse_time_string,
    ensure_slicer_profiles_dir,
    is_quotable_format,
    normalize_scale_percent,
    slicer_profile_path,
    task_envelope,
)
from app.services import runtime_checks


# ---------------------------------------------------------------------------
# Issue 10 — materials
# ---------------------------------------------------------------------------


def test_material_defaults_table_has_expected_entries():
    assert MATERIAL_DEFAULTS["PLA"] == {"density": 1.24, "default_temp": 215}
    assert MATERIAL_DEFAULTS["PETG"]["density"] == 1.27
    assert MATERIAL_DEFAULTS["TPU"]["default_temp"] == 225


def test_resolve_density_manual_wins_over_embedded_and_default():
    density, source = resolve_density("PLA", embedded=1.30, manual=1.40)
    assert density == Decimal("1.40")
    assert source == "manual"


def test_resolve_density_embedded_beats_default():
    density, source = resolve_density("PLA", embedded=1.30)
    assert density == Decimal("1.30")
    assert source == "embedded"


def test_resolve_density_default_from_material_table():
    density, source = resolve_density("PETG")
    assert density == Decimal("1.27")
    assert source == "default"


def test_resolve_density_unknown_material_falls_back_to_default():
    density, source = resolve_density("UNKNOWN_RESIN")
    assert source == "default"
    assert density == Decimal("1.24")


def test_resolve_density_case_insensitive():
    density, _ = resolve_density("pla")
    assert density == Decimal("1.24")


def test_material_default_temp():
    assert material_default_temp("ABS") == 250
    assert material_default_temp("asa") == 260
    assert material_default_temp("carbon-fiber") is None


# ---------------------------------------------------------------------------
# Issue 12 — gcode parsing across Prusa / Bambu / Orca
# ---------------------------------------------------------------------------


def test_gcode_parser_prusa_total_filament_and_normal_mode_time(tmp_path):
    path = tmp_path / "quote.gcode"
    path.write_text(
        "; total filament used [g] = 56.58\n"
        "; estimated printing time (normal mode) = 1d 2h 3m 30s\n"
        "; total layers count: 422\n",
        encoding="utf-8",
    )
    result = _parse_gcode_stats(path)
    assert result is not None
    assert result["filament_grams"] == Decimal("56.58")
    assert result["print_minutes"] == Decimal("1563.5")
    assert result["layer_count"] == 422
    assert result["filament_source_pattern"] == "total_filament_used_g"
    assert result["time_source_pattern"] == "estimated_printing_time_normal"


def test_gcode_parser_bambu_filament_used_g(tmp_path):
    path = tmp_path / "bambu.gcode"
    path.write_text(
        "; filament used [g] = 18.42\n"
        "; total estimated time = 42m 15s\n",
        encoding="utf-8",
    )
    result = _parse_gcode_stats(path)
    assert result is not None
    assert result["filament_grams"] == Decimal("18.42")
    assert result["filament_source_pattern"] == "filament_used_g"
    assert result["time_source_pattern"] == "total_estimated_time"
    assert result["print_minutes"] == Decimal(str(42 + 15 / 60))


def test_gcode_parser_orca_estimated_time(tmp_path):
    path = tmp_path / "orca.gcode"
    path.write_text(
        "; total filament used [g] = 9.00\n"
        "; estimated time = 1h 5m\n",
        encoding="utf-8",
    )
    result = _parse_gcode_stats(path)
    assert result is not None
    assert result["time_source_pattern"] == "estimated_time"
    assert result["print_minutes"] == Decimal("65")


def test_gcode_parser_total_filament_cost(tmp_path):
    path = tmp_path / "cost.gcode"
    path.write_text(
        "; total filament used [g] = 5.00\n"
        "; total filament cost = 0.42\n"
        "; estimated printing time = 10m\n",
        encoding="utf-8",
    )
    result = _parse_gcode_stats(path)
    assert result is not None
    assert result["filament_cost"] == Decimal("0.42")
    assert result["cost_source_pattern"] == "total_filament_cost"


def test_gcode_parser_cm3_volume_fallback_uses_density(tmp_path):
    path = tmp_path / "vol.gcode"
    path.write_text(
        "; filament used [cm3] = 10.00\n"
        "; estimated print time = 10m\n",
        encoding="utf-8",
    )
    result = _parse_gcode_stats(path, density=Decimal("1.27"))
    assert result["filament_grams"] == Decimal("12.70")
    assert result["filament_source_pattern"] == "filament_used_cm3"


def test_time_parser_supports_days():
    assert _parse_time_string("2d 1h 5m") == 2945


# ---------------------------------------------------------------------------
# Issue 5 — task envelope
# ---------------------------------------------------------------------------


def test_task_envelope_success_default_data():
    env = task_envelope(True)
    assert env == {"success": True, "data": {}, "error": ""}


def test_task_envelope_failure_with_error():
    env = task_envelope(False, error="boom")
    assert env["success"] is False
    assert env["error"] == "boom"
    assert env["data"] == {}


def test_task_envelope_carries_data():
    env = task_envelope(True, data={"product_id": 7, "grams": "12.5"})
    assert env["success"] is True
    assert env["data"]["product_id"] == 7
    assert env["error"] == ""


# ---------------------------------------------------------------------------
# Issue 8 — quotable vs preview formats
# ---------------------------------------------------------------------------


def test_quotable_formats_include_stl_3mf_obj():
    assert QUOTABLE_FORMATS == frozenset({".stl", ".3mf", ".obj"})


def test_preview_only_formats_include_glb_gltf():
    assert PREVIEW_ONLY_FORMATS == frozenset({".glb", ".gltf"})


def test_is_quotable_format():
    assert is_quotable_format("dragon.stl") is True
    assert is_quotable_format("D:/models/DRAGON.3MF") is True
    assert is_quotable_format("preview.glb") is False
    assert is_quotable_format("scene.gltf") is False
    assert is_quotable_format("notes.txt") is False


# ---------------------------------------------------------------------------
# Issue 23/49 — slicer profile path bare-name resolution
# ---------------------------------------------------------------------------


def test_slicer_profile_path_bare_name_appends_ini():
    bare = slicer_profile_path("bambu_a1")
    assert bare.name == "bambu_a1.ini"
    assert bare.exists()


def test_slicer_profile_path_full_name_still_resolves():
    full = slicer_profile_path("bambu_x1c.ini")
    assert full.name == "bambu_x1c.ini"
    assert full.exists()


def test_slicer_profile_path_missing_falls_back_to_default():
    path = slicer_profile_path("does_not_exist")
    assert path.name == "bambu_a1.ini"


def test_slicer_profile_path_none_uses_default():
    path = slicer_profile_path(None)
    assert path.name == "bambu_a1.ini"


def test_ensure_slicer_profiles_dir_is_noop_when_present(tmp_path):
    # The real profiles dir already exists; calling again should not raise.
    result = ensure_slicer_profiles_dir()
    assert result.exists()


# ---------------------------------------------------------------------------
# Issue 32 / 4 — runtime checks
# ---------------------------------------------------------------------------


def test_runtime_health_shape_with_mocked_slicer_service():
    with mock.patch.object(runtime_checks, "check_trimesh_available", return_value=True), \
            mock.patch.object(runtime_checks, "check_slicer_service_available", return_value=True):
        health = runtime_checks.runtime_health()
    assert health == {"trimesh": True, "prusaslicer": True}


def test_check_prusaslicer_available_returns_false_on_file_not_found():
    with mock.patch.object(
        runtime_checks.subprocess, "run", side_effect=FileNotFoundError
    ):
        assert runtime_checks.check_prusaslicer_available() is False


def test_check_prusaslicer_available_uses_env_path():
    fake_proc = mock.Mock(returncode=0)
    with mock.patch.dict("os.environ", {"PRUSA_SLICER_PATH": "/custom/prusa"}), \
            mock.patch.object(runtime_checks.subprocess, "run", return_value=fake_proc) as run_mock:
        assert runtime_checks.check_prusaslicer_available() is True
    assert run_mock.call_args.args[0][0] == "/custom/prusa"


def test_check_prusaslicer_available_returns_false_on_nonzero_exit():
    fake_proc = mock.Mock(returncode=1)
    with mock.patch.object(runtime_checks.subprocess, "run", return_value=fake_proc):
        assert runtime_checks.check_prusaslicer_available() is False


def test_is_celery_healthy_returns_true_on_ping():
    with mock.patch("app.celery_app.celery") as celery_mock:
        celery_mock.control.ping.return_value = [{"celery@host": {"ok": "pong"}}]
        assert runtime_checks.is_celery_healthy() is True


def test_is_celery_healthy_returns_false_on_error():
    with mock.patch("app.celery_app.celery") as celery_mock:
        celery_mock.control.ping.side_effect = RuntimeError("broker down")
        assert runtime_checks.is_celery_healthy() is False


def test_is_celery_healthy_returns_false_on_import_error():
    with mock.patch("builtins.__import__", side_effect=ImportError):
        assert runtime_checks.is_celery_healthy() is False


# ---------------------------------------------------------------------------
# Issue 11 — scene handling (requires trimesh)
# ---------------------------------------------------------------------------


def _trimesh_available() -> bool:
    try:
        import trimesh  # noqa: F401
    except Exception:
        return False
    return True


def test_apply_scale_doubles_a_cube(tmp_path):
    if not _trimesh_available():
        pytest.skip("trimesh not installed")
    import trimesh

    from app.services.model_analysis import apply_scale

    cube = trimesh.creation.box(extents=[10, 10, 10])
    src = tmp_path / "cube.stl"
    cube.export(str(src))
    scaled = apply_scale(src, 200)
    # 2x scale on a 10mm cube -> 20mm side -> 8000 mm^3 volume.
    assert scaled is not None
    assert abs(float(scaled.volume) - 8000.0) < 1.0


# ---------------------------------------------------------------------------
# Regression — scale_percent is stored as a stringified Decimal ("100.00")
# ---------------------------------------------------------------------------


def test_normalize_scale_percent_coerces_decimal_string():
    assert normalize_scale_percent("100.00") == 100
    assert normalize_scale_percent("100.0") == 100
    assert normalize_scale_percent("100") == 100
    assert normalize_scale_percent(Decimal("100.00")) == 100
    assert normalize_scale_percent(100) == 100
    assert normalize_scale_percent(104.5) == 104


def test_normalize_scale_percent_none_and_empty_are_none():
    assert normalize_scale_percent(None) is None
    assert normalize_scale_percent("") is None
    assert normalize_scale_percent("  ") is None


def test_normalize_scale_percent_bad_value_returns_none():
    assert normalize_scale_percent("abc") is None
    assert normalize_scale_percent("NaN") is None


def test_cost_snapshot_accepts_decimal_string_scale_percent(app):
    """The cost snapshot int column must not reject '100.00' (regression)."""
    from app.extensions import db
    from app.models import Category, CostSnapshot, Product, ProductStatus, ProductType
    from app.tasks.model_analysis import _apply_initial_cost_snapshot

    with app.app_context():
        category = Category(name="Snap", slug="snap", is_public=True, is_pos_visible=True)
        product = Product(
            name="Snap Product",
            slug="snap-product",
            sku_base="SNAP-1",
            category=category,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            base_price=20,
        )
        product.analysis_status = "complete"
        product.parsed_filament_grams = Decimal("42.00")
        product.parsed_print_minutes = Decimal("84.00")
        product.parsed_volume_mm3 = Decimal("1000.00")
        product.model_file_path = "/tmp/snapshot.stl"
        db.session.add(category)
        db.session.add(product)
        db.session.flush()

        _apply_initial_cost_snapshot(
            product,
            run_id=None,
            material="PLA",
            scale_percent="100.00",
            copies=1,
            cost_resolver_evidence=None,
        )
        db.session.commit()

        snapshot = CostSnapshot.query.filter_by(product_id=product.id, stale=False).first()
        assert snapshot is not None
        assert snapshot.scale_percent == 100
        assert snapshot.copies == 1


def test_coerce_to_mesh_merges_scene():
    """A trimesh Scene (multi-mesh) is concatenated into one mesh (Issue 11)."""
    if not _trimesh_available():
        pytest.skip("trimesh not installed")
    import trimesh

    from app.services.model_analysis import _coerce_to_mesh

    a = trimesh.creation.box(extents=[10, 10, 10])
    b = trimesh.creation.box(extents=[5, 5, 5])
    b.apply_translation([20, 0, 0])
    scene = trimesh.Scene([a, b])
    assert hasattr(scene, "geometry") and scene.geometry

    mesh, warning = _coerce_to_mesh(scene)
    assert warning is None
    assert mesh is not None
    # Merged volume = 1000 (10mm cube) + 125 (5mm cube) = 1125 mm^3.
    assert abs(float(mesh.volume) - 1125.0) < 2.0


def test_validate_model_file_handles_multi_mesh_obj(tmp_path):
    """load_mesh already merges multi-mesh OBJs; validate must still succeed."""
    if not _trimesh_available():
        pytest.skip("trimesh not installed")
    import trimesh

    from app.services.model_analysis import validate_model_file

    a = trimesh.creation.box(extents=[10, 10, 10])
    b = trimesh.creation.box(extents=[5, 5, 5])
    b.apply_translation([20, 0, 0])
    scene = trimesh.Scene([a, b])
    scene_path = tmp_path / "multi.obj"
    scene.export(str(scene_path), file_type="obj")
    result = validate_model_file(scene_path)
    assert result.success is True
    assert abs(result.volume_mm3 - 1125.0) < 2.0


# ---------------------------------------------------------------------------
# Issue 37 — PMP printer profile (smoke-level: profile stem derivation)
# ---------------------------------------------------------------------------


def test_printer_build_volumes_has_bambu_a1():
    from app.services.model_analysis import PRINTER_BUILD_VOLUMES

    assert PRINTER_BUILD_VOLUMES["bambu_a1"] == {"x": 256, "y": 256, "z": 256}