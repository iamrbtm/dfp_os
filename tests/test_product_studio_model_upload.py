from __future__ import annotations

import io

from flask import Flask

from app.blueprints.products import studio_routes
from app.forms.studio import ProductModelUploadForm
from app.services.product_analysis import sanitize_analysis_config


def _model_upload_data(**overrides):
    data = {
        "model_file": (io.BytesIO(b"solid test\nendsolid test\n"), "part.stl"),
        "printer_profile": "bambu_a1",
        "material": "PLA",
        "filament_density": "1.24",
        "nozzle_diameter": "0.4",
        "layer_height": "0.2",
        "perimeters": "2",
        "top_solid_layers": "3",
        "bottom_solid_layers": "3",
        "infill_percent": "20",
        "infill_pattern": "cubic",
        "supports": "none",
        "brim_width": "0",
        "copies": "1",
        "scale_percent": "100",
    }
    data.update(overrides)
    return data


def test_model_upload_form_uses_bare_bambu_profile_keys():
    test_app = Flask(__name__)
    test_app.config.update(SECRET_KEY="test", WTF_CSRF_ENABLED=False)
    with test_app.app_context():
        form = ProductModelUploadForm(meta={"csrf": False})
    assert [value for value, _ in form.printer_profile.choices] == [
        "bambu_a1",
        "bambu_x1c",
        "bambu_p1p",
    ]


def test_sanitize_analysis_config_normalizes_legacy_ini_profile():
    assert (
        sanitize_analysis_config({"printer_profile": "bambu_a1.ini"})["printer_profile"]
        == "bambu_a1"
    )


def test_upload_model_rejects_tampered_nozzle_without_enqueue(client, login_admin, monkeypatch):
    class _UnexpectedCelery:
        def delay(self, *args, **kwargs):
            raise AssertionError("analysis must not be enqueued for invalid upload settings")

    monkeypatch.setattr(studio_routes, "get_by_id", lambda model, resource_id: object())
    monkeypatch.setattr(studio_routes, "_get_celery", lambda: _UnexpectedCelery())
    response = client.post(
        "/products/studio/123/upload-model",
        data=_model_upload_data(nozzle_diameter="0.6"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "Nozzle diameter" in payload["error"]


def test_upload_model_rejects_invalid_printer_without_enqueue(client, login_admin, monkeypatch):
    class _UnexpectedCelery:
        def delay(self, *args, **kwargs):
            raise AssertionError("analysis must not be enqueued for invalid upload settings")

    monkeypatch.setattr(studio_routes, "get_by_id", lambda model, resource_id: object())
    monkeypatch.setattr(studio_routes, "_get_celery", lambda: _UnexpectedCelery())
    response = client.post(
        "/products/studio/123/upload-model",
        data=_model_upload_data(printer_profile="/opt/bambu/profile.ini"),
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "Printer profile" in payload["error"]
