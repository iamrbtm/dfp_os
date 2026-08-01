from __future__ import annotations

from flask import Flask

from app.models import Product
from app.services.storage import (
    converted_storage_key,
    gcode_storage_key,
    image_storage_key,
    legacy_gcode_storage_key,
    list_product_assets,
    metadata_storage_key,
    normalize_storage_filename,
    product_storage_key,
    planned_storage_reference,
    storage_slug,
)
from app.tasks.model_analysis import (
    _preferred_converted_filename,
    _preferred_gcode_filename,
)


def test_product_storage_keys_use_one_product_directory():
    assert product_storage_key(14, "56eb2eba.stl") == "products/14/56eb2eba.stl"
    assert converted_storage_key(14, "56eb2eba.glb") == "products/14/56eb2eba.glb"
    assert gcode_storage_key(14, "rainbow-dragon.gcode", run_id=41) == (
        "products/14/analysis-runs/41/rainbow-dragon.gcode"
    )
    assert gcode_storage_key(14, "rainbow-dragon.gcode.3mf", run_id=42) == (
        "products/14/analysis-runs/42/rainbow-dragon.gcode.3mf"
    )
    assert image_storage_key(14, "IMG_0204.jpeg") == "products/14/IMG_0204.jpeg"
    assert metadata_storage_key(14, "model.metadata.json") == "products/14/model.metadata.json"


def test_local_product_asset_listing_is_product_scoped(app, tmp_path):
    app.config.update(FILE_STORAGE_BACKEND="local")
    target = tmp_path / "products" / "14"
    target.mkdir(parents=True)
    (target / "dragon.stl").write_bytes(b"mesh")
    other = tmp_path / "products" / "15"
    other.mkdir(parents=True)
    (other / "other.stl").write_bytes(b"other")

    with app.app_context():
        assets = list_product_assets(14, bucket="products", local_root=tmp_path)

    assert [asset["name"] for asset in assets] == ["dragon.stl"]


def test_storage_filename_helpers_normalize_expected_values():
    assert normalize_storage_filename("IMG 0204.JPEG") == "IMG_0204.jpeg"
    assert normalize_storage_filename("Rainbow Dragon.gcode.3MF") == ("Rainbow_Dragon.gcode.3mf")
    assert storage_slug("Rainbow Dragon XL") == "rainbow_dragon_xl"


def test_gcode_storage_keys_are_immutable_per_run_and_safely_normalized():
    first = gcode_storage_key(14, "../Rainbow Dragon.gcode.3MF", run_id=101)
    second = gcode_storage_key(14, "../Rainbow Dragon.gcode.3MF", run_id=102)

    assert first == "products/14/analysis-runs/101/Rainbow_Dragon.gcode.3mf"
    assert second == "products/14/analysis-runs/102/Rainbow_Dragon.gcode.3mf"
    assert first != second


def test_legacy_gcode_migration_key_is_deterministic_and_cannot_collide_with_runs():
    legacy = legacy_gcode_storage_key(14, "Rainbow Dragon.gcode.3MF")

    assert legacy == "products/14/legacy-migration/Rainbow_Dragon.gcode.3mf"
    assert legacy != gcode_storage_key(14, "Rainbow Dragon.gcode.3MF", run_id=101)


def test_planned_local_reference_is_exact_before_copy(tmp_path):
    app = Flask(__name__)
    app.config["FILE_STORAGE_BACKEND"] = "local"

    with app.app_context():
        reference = planned_storage_reference(
            bucket="products",
            key="products/14/analysis-runs/101/dragon.gcode.3mf",
            local_root=tmp_path,
        )

    assert reference == str((tmp_path / "products/14/analysis-runs/101/dragon.gcode.3mf").resolve())


def test_local_product_asset_listing_recurses_nested_run_keys_without_symlink_escape(tmp_path):
    app = Flask(__name__)
    app.config["FILE_STORAGE_BACKEND"] = "local"
    product_root = tmp_path / "products" / "14"
    nested = product_root / "analysis-runs" / "101"
    nested.mkdir(parents=True)
    (nested / "dragon.gcode.3mf").write_bytes(b"native")
    outside = tmp_path / "outside.gcode"
    outside.write_bytes(b"outside")
    (product_root / "escaped.gcode").symlink_to(outside)

    with app.app_context():
        assets = list_product_assets(14, bucket="products", local_root=tmp_path)

    assert [asset["name"] for asset in assets] == ["analysis-runs/101/dragon.gcode.3mf"]
    assert assets[0]["reference"] == str((nested / "dragon.gcode.3mf").resolve())


def test_analysis_output_filenames_follow_product_convention():
    product = Product(
        id=14, slug="rainbow-dragon", model_file_path="s3://products/products/14/56eb2eba.stl"
    )

    assert _preferred_gcode_filename(product, "bambu") == "rainbow-dragon.gcode.3mf"
    assert _preferred_gcode_filename(product, "prusa") == "rainbow-dragon.gcode"
    assert _preferred_converted_filename(product) == "56eb2eba.glb"


def test_analysis_output_filenames_fallback_cleanly():
    product = Product(id=14, slug="rainbow-dragon", model_file_path="/tmp/Rainbow Dragon.stl")

    assert _preferred_gcode_filename(product, "bambu") == "rainbow-dragon.gcode.3mf"
    assert _preferred_gcode_filename(product, "prusa") == "rainbow-dragon.gcode"
    assert _preferred_converted_filename(product) == "Rainbow_Dragon.glb"
