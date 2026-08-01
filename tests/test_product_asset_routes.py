from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask
from werkzeug.exceptions import NotFound

from app.blueprints.products import studio_routes


def _product(product_id: int = 14):
    return SimpleNamespace(
        id=product_id,
        business_id=3,
        model_file_path=None,
        converted_model_path=None,
        gcode_path=None,
        model_metadata_path=None,
        default_image_path=None,
        pos_image_path=None,
        images=[],
    )


def _app(tmp_path):
    app = Flask(__name__)
    app.config.update(
        PRODUCT_ASSETS_BUCKET="products",
        PRODUCT_ASSETS_PATH=str(tmp_path),
        FILE_STORAGE_BACKEND="local",
    )
    return app


def test_nested_analysis_asset_download_uses_authorized_listed_reference(tmp_path, monkeypatch):
    app = _app(tmp_path)
    product = _product()
    name = "analysis-runs/101/dragon.gcode.3mf"
    reference = str((tmp_path / "products/14" / name).resolve())
    monkeypatch.setattr(studio_routes, "get_by_id", lambda model, identity: product)
    monkeypatch.setattr(
        studio_routes,
        "list_product_assets",
        lambda *args, **kwargs: [{"name": name, "reference": reference}],
    )
    monkeypatch.setattr(
        studio_routes,
        "send_storage_reference",
        lambda selected, **kwargs: (selected, kwargs["download_name"]),
    )

    with app.test_request_context(f"/studio/14/assets/{name}"):
        result = studio_routes.download_product_asset.__wrapped__(14, name)

    assert result == (reference, name)


def test_nested_analysis_asset_delete_uses_authorized_listed_reference(tmp_path, monkeypatch):
    app = _app(tmp_path)
    product = _product()
    name = "analysis-runs/101/dragon.gcode.3mf"
    reference = str((tmp_path / "products/14" / name).resolve())
    deleted: list[str] = []
    audits: list[dict] = []
    monkeypatch.setattr(studio_routes, "get_by_id", lambda model, identity: product)
    monkeypatch.setattr(
        studio_routes,
        "list_product_assets",
        lambda *args, **kwargs: [{"name": name, "reference": reference}],
    )
    monkeypatch.setattr(studio_routes, "delete_storage_reference", deleted.append)
    monkeypatch.setattr(studio_routes.db.session, "commit", lambda: None)
    monkeypatch.setattr(studio_routes, "current_user", SimpleNamespace(id=9, display_name="Owner"))
    monkeypatch.setattr(
        studio_routes,
        "get_audit_client",
        lambda: SimpleNamespace(record=lambda **kwargs: audits.append(kwargs)),
    )

    with app.test_request_context(f"/studio/14/assets/{name}"):
        response = studio_routes.delete_product_asset.__wrapped__(14, name)

    assert response.get_json() == {
        "success": True,
        "deleted": name,
        "metadata_deleted": False,
    }
    assert deleted == [reference]
    assert audits[0]["metadata"]["kind"] == "gcode"


@pytest.mark.parametrize(
    "name",
    (
        "../dragon.stl",
        "/etc/passwd",
        "analysis-runs/101/../../dragon.stl",
        "analysis-runs/not-a-run/dragon.gcode",
        "analysis-runs/101/nested/dragon.gcode",
        "products/15/dragon.stl",
        r"analysis-runs\101\dragon.gcode",
    ),
)
@pytest.mark.parametrize("route_name", ("download_product_asset", "delete_product_asset"))
def test_asset_routes_reject_traversal_absolute_and_foreign_paths(
    tmp_path,
    monkeypatch,
    name,
    route_name,
):
    app = _app(tmp_path)
    monkeypatch.setattr(studio_routes, "get_by_id", lambda model, identity: _product())
    monkeypatch.setattr(
        studio_routes,
        "list_product_assets",
        lambda *args, **kwargs: pytest.fail("unsafe names must fail before storage listing"),
    )
    route = getattr(studio_routes, route_name).__wrapped__

    with app.test_request_context("/studio/14/assets/rejected"):
        with pytest.raises(NotFound):
            route(14, name)
