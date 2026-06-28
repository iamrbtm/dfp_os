from __future__ import annotations

from app.models import Product
from app.services.storage import (
    converted_storage_key,
    gcode_storage_key,
    image_storage_key,
    normalize_storage_filename,
    product_storage_key,
    storage_slug,
)
from app.tasks.model_analysis import (
    _preferred_converted_filename,
    _preferred_gcode_filename,
)


def test_product_storage_keys_use_one_product_directory():
    assert product_storage_key(14, "56eb2eba.stl") == "products/14/56eb2eba.stl"
    assert converted_storage_key(14, "56eb2eba.glb") == "products/14/56eb2eba.glb"
    assert gcode_storage_key(14, "rainbow-dragon.gcode") == "products/14/rainbow-dragon.gcode"
    assert image_storage_key(14, "IMG_0204.jpeg") == "products/14/IMG_0204.jpeg"


def test_storage_filename_helpers_normalize_expected_values():
    assert normalize_storage_filename("IMG 0204.JPEG") == "IMG_0204.jpeg"
    assert storage_slug("Rainbow Dragon XL") == "rainbow_dragon_xl"


def test_analysis_output_filenames_follow_product_convention():
    product = Product(id=14, slug="rainbow-dragon", model_file_path="s3://products/products/14/56eb2eba.stl")

    assert _preferred_gcode_filename(product) == "rainbow-dragon.gcode"
    assert _preferred_converted_filename(product) == "56eb2eba.glb"


def test_analysis_output_filenames_fallback_cleanly():
    product = Product(id=14, slug="rainbow-dragon", model_file_path="/tmp/Rainbow Dragon.stl")

    assert _preferred_gcode_filename(product) == "rainbow-dragon.gcode"
    assert _preferred_converted_filename(product) == "Rainbow_Dragon.glb"
