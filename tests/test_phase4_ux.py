"""Phase 4 — UI, UX & user-feedback tests (Issues 3, 5/36, 16, 17, 22, 34)."""

from __future__ import annotations

import io

from PIL import Image

from app.blueprints.products import studio_routes
from app.extensions import db
from app.models import (
    AnalysisRunStatus,
    CostSnapshot,
    LicenseStatus,
    ModelSourceType,
    Product,
    ProductAnalysisRun,
    ProductImage,
    ProductStatus,
    ProductType,
)
from app.services.image_validation import validate_image_file


def test_product_studio_renders_current_analysis_engine_metadata(
    app, client, login_admin, monkeypatch
):
    product = Product(
        id=123,
        name="Metadata Dragon",
        slug="metadata-dragon",
        sku_base="META-DRAGON",
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
        license_status=LicenseStatus.UNKNOWN,
        model_source_type=ModelSourceType.UNKNOWN,
        model_file_path="local://products/part.stl",
    )
    product.analysis_runs.append(
        ProductAnalysisRun(
            product_id=123,
            source_asset_id=1,
            status=AnalysisRunStatus.COMPLETE,
            is_current=True,
            slicer_stats_json={
                "engine_name": "Bambu Studio",
                "engine_version": "2.7.1.62",
                "profile_ids": {
                    "machine": "Bambu Lab A1 0.4 nozzle",
                    "process": "0.20mm Standard @BBL A1",
                    "filament": "Generic PLA @BBL A1",
                },
                "artifact_media_type": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
                "direct_print_eligible": True,
                "fallback_used": False,
                "primary_failure": None,
            },
        )
    )
    monkeypatch.setattr(studio_routes, "ensure_product_ops_defaults", lambda product: None)
    monkeypatch.setattr(studio_routes, "sync_launch_checklist", lambda product: [])
    monkeypatch.setattr(studio_routes, "calculate_product_readiness", lambda product: {})
    monkeypatch.setattr(studio_routes, "_load_products", lambda: [product])
    monkeypatch.setattr(studio_routes, "get_by_id", lambda model, resource_id: product)

    response = client.get("/products/studio/123")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Bambu Studio" in html
    assert "2.7.1.62" in html
    assert "Bambu Lab A1 0.4 nozzle" in html
    assert "0.20mm Standard @BBL A1" in html
    assert "Generic PLA @BBL A1" in html
    assert "Native .gcode.3mf" in html
    assert "Direct print eligible" in html


# ---------------------------------------------------------------------------
# Issue 16 — manual cost calculation must not look successful without a model
# ---------------------------------------------------------------------------


def test_calculate_costs_no_model_returns_409(app, client, login_admin, catalog_product):
    # catalog_product has no model analysis, so model_ready is False.
    r = client.post(
        f"/products/studio/{catalog_product}/calculate-costs",
        json={},
    )
    assert r.status_code == 409
    payload = r.get_json()
    assert payload["status"] == "no_model"
    assert payload["success"] is False
    assert payload["confidence"] == "none"
    # No snapshot should have been created for a blocked calculation.
    with app.app_context():
        assert db.session.query(CostSnapshot).filter_by(product_id=catalog_product).count() == 0


def test_calculate_costs_confirm_no_model_succeeds(app, client, login_admin, catalog_product):
    r = client.post(
        f"/products/studio/{catalog_product}/calculate-costs",
        json={"confirm_no_model": True},
    )
    assert r.status_code == 200, r.get_json()
    payload = r.get_json()
    assert payload["success"] is True
    assert payload["status"] == "complete"
    data = payload["data"]
    # Without a model the confidence is "none" and a warning is surfaced.
    assert data["confidence"] == "none"
    assert data["model_ready"] is False
    assert data["warning"] is not None
    assert data["snapshot_id"] is not None


def test_cost_result_includes_confidence(app, client, login_admin, catalog_product):
    r = client.get(f"/products/studio/cost-result/{catalog_product}")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["success"] is True
    assert "confidence" in payload
    assert "evidence_source" in payload


# ---------------------------------------------------------------------------
# Issue 5/36 — task-status envelope; a failed analysis must not read as complete
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, state, result=None, info=None):
        self.state = state
        self.result = result
        self.info = info


class _FakeCelery:
    def __init__(self, result):
        self._result = result

    def AsyncResult(self, task_id):  # noqa: N802 - mirrors Celery API
        return self._result


def test_task_status_failed_analysis_envelope(app, client, login_admin, monkeypatch):
    # A task that finished (Celery SUCCESS) but returned success:false must be
    # reported as a failure, not "complete".
    fake = _FakeCelery(
        _FakeResult("SUCCESS", result={"success": False, "data": None, "error": "boom"})
    )
    monkeypatch.setattr(studio_routes, "_get_celery", lambda: fake)

    r = client.get("/products/studio/task-status/abc")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["success"] is False
    assert payload["status"] == "failed"
    assert payload["error"] == "boom"


def test_task_status_success_envelope(app, client, login_admin, monkeypatch):
    fake = _FakeCelery(
        _FakeResult("SUCCESS", result={"success": True, "data": {"x": 1}, "error": ""})
    )
    monkeypatch.setattr(studio_routes, "_get_celery", lambda: fake)

    r = client.get("/products/studio/task-status/abc")
    payload = r.get_json()
    assert payload["success"] is True
    assert payload["status"] == "complete"
    assert payload["data"] == {"x": 1}


def test_task_status_progress_uses_substatus(app, client, login_admin, monkeypatch):
    fake = _FakeCelery(_FakeResult("PROGRESS", info={"status": "slicing", "percent": 40}))
    monkeypatch.setattr(studio_routes, "_get_celery", lambda: fake)

    r = client.get("/products/studio/task-status/abc")
    payload = r.get_json()
    assert payload["success"] is True
    assert payload["status"] == "slicing"
    assert payload["data"]["percent"] == 40


# ---------------------------------------------------------------------------
# Issue 3 — form validation failure returns 400, not 200
# ---------------------------------------------------------------------------


def test_studio_create_invalid_form_returns_400(app, client, login_admin):
    with app.app_context():
        from app.models import Category

        cat = Category(name="P4Cat", slug="p4cat", is_public=True, is_pos_visible=True)
        db.session.add(cat)
        db.session.commit()
        cid = cat.id
    # Missing required name → form validation fails.
    r = client.post(
        "/products/studio",
        data={
            "name": "",
            "slug": "",
            "sku_base": "",
            "category_id": str(cid),
            "product_type": "finished_good",
            "status": "draft",
            "license_status": "original",
            "model_source_type": "original",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Issue 22 — image content validation (magic bytes, not just extension)
# ---------------------------------------------------------------------------


def test_validate_image_file_accepts_real_png(tmp_path):
    path = tmp_path / "real.png"
    Image.new("RGB", (8, 8), "red").save(path, "PNG")
    error, mime = validate_image_file(path)
    assert error is None
    assert mime == "image/png"


def test_validate_image_file_rejects_non_image(tmp_path):
    path = tmp_path / "fake.jpg"
    path.write_bytes(b"this is definitely not an image")
    error, mime = validate_image_file(path)
    assert error is not None
    assert mime is None


def test_upload_image_rejects_non_image_content(app, client, login_admin, catalog_product):
    # A file named photo.jpg whose bytes are not an image must be rejected
    # even though the extension is allowed.
    r = client.post(
        f"/products/studio/{catalog_product}/upload-image",
        data={"image": (io.BytesIO(b"not an image at all"), "photo.jpg")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    assert r.get_json()["success"] is False
    with app.app_context():
        assert db.session.query(ProductImage).filter_by(product_id=catalog_product).count() == 0


def test_upload_image_rejects_oversize(app, client, login_admin, catalog_product):
    # Build a real (small) PNG, then force a tiny image size cap so the upload
    # is rejected as too large before any DB row is created.
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buf, "PNG")
    png_bytes = buf.getvalue()
    app.config["PRODUCT_IMAGE_MAX_BYTES"] = len(png_bytes) - 1

    r = client.post(
        f"/products/studio/{catalog_product}/upload-image",
        data={"image": (io.BytesIO(png_bytes), "tiny.png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 413
    assert r.get_json()["success"] is False
    with app.app_context():
        assert db.session.query(ProductImage).filter_by(product_id=catalog_product).count() == 0


def test_upload_image_accepts_real_png(app, client, login_admin, catalog_product):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buf, "PNG")
    r = client.post(
        f"/products/studio/{catalog_product}/upload-image",
        data={"image": (io.BytesIO(buf.getvalue()), "green.png"), "alt_text": "A green square"},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.get_json()
    payload = r.get_json()
    assert payload["success"] is True
    assert payload["image_id"] is not None
    with app.app_context():
        img = db.session.get(ProductImage, payload["image_id"])
        assert img is not None
        assert img.alt_text == "A green square"
