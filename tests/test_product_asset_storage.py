from __future__ import annotations

from app.models import ModelAsset, Product, ProductVariant
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


def test_variant_storage_keys_share_one_variant_directory():
    assert product_storage_key(14, "56eb2eba.stl", variant_id=16) == "products/14/variants/16/56eb2eba.stl"
    assert converted_storage_key(14, "16_56eb2eba.glb", variant_id=16) == "products/14/variants/16/16_56eb2eba.glb"
    assert gcode_storage_key(14, "medium.gcode", variant_id=16) == "products/14/variants/16/medium.gcode"
    assert image_storage_key(14, "IMG_0204.jpeg", variant_id=16) == "products/14/variants/16/IMG_0204.jpeg"


def test_product_level_storage_keys_use_product_root_directory():
    assert product_storage_key(14, "master.stl") == "products/14/master.stl"
    assert converted_storage_key(14, "master.glb") == "products/14/master.glb"
    assert gcode_storage_key(14, "rainbow-dragon.gcode") == "products/14/rainbow-dragon.gcode"
    assert image_storage_key(14, "hero.jpeg") == "products/14/hero.jpeg"


def test_storage_filename_helpers_match_variant_layout_expectations():
    assert normalize_storage_filename("IMG 0204.JPEG") == "IMG_0204.jpeg"
    assert storage_slug("Medium") == "medium"
    assert storage_slug("Rainbow Dragon XL") == "rainbow_dragon_xl"


def test_analysis_output_filenames_follow_variant_folder_convention():
    product = Product(id=14, slug="rainbow-dragon")
    variant = ProductVariant(id=16, product_id=14, size="Medium", name="Medium")
    asset = ModelAsset(id=9, related_product_id=14, variant_id=16, file_location="s3://products/products/14/variants/16/56eb2eba035947a482f6f71a2d390c3a.stl")
    asset.product = product
    asset.variant = variant

    assert _preferred_gcode_filename(asset) == "medium.gcode"
    assert _preferred_converted_filename(asset) == "16_56eb2eba035947a482f6f71a2d390c3a.glb"


def test_analysis_output_filenames_fallback_cleanly_for_product_level_assets():
    product = Product(id=14, slug="rainbow-dragon")
    asset = ModelAsset(id=9, related_product_id=14, file_location="/tmp/Rainbow Dragon.stl")
    asset.product = product

    assert _preferred_gcode_filename(asset) == "rainbow-dragon.gcode"
    assert _preferred_converted_filename(asset) == "Rainbow_Dragon.glb"
