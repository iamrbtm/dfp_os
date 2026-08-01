from __future__ import annotations

import base64
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.services import model_analysis
from app.services.model_analysis import slice_with_prusaslicer, slice_with_slicer
from app.services import slicer_client


def _metadata(payload: bytes, **overrides):
    metadata = {
        "success": True,
        "engine_key": "bambu",
        "engine_name": "Bambu Studio",
        "engine_version": "2.7.1.62",
        "fallback_used": False,
        "primary_failure": None,
        "filament_grams": "12.5",
        "print_minutes": "42",
        "layer_count": 210,
        "profile_ids": {
            "machine": "Bambu Lab A1 0.4 nozzle",
            "process": "0.20mm Standard @BBL A1",
            "filament": "Generic PLA @BBL A1",
        },
        "artifact_filename": "dragon.gcode.3mf",
        "artifact_media_type": "application/vnd.bambulab.gcode-3mf",
        "artifact_size": len(payload),
        "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "direct_print_eligible": True,
        "estimate_only": False,
    }
    metadata.update(overrides)
    return metadata


def _metadata_header(metadata: dict, *, padded: bool = False) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(metadata, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii")
    return encoded if padded else encoded.rstrip("=")


def _call_artifact_client(
    tmp_path,
    metadata: dict,
    payload: bytes,
    *,
    padded: bool = False,
    response_headers: dict[str, str] | None = None,
    encoded_metadata: str | None = None,
):
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "artifacts"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(exist_ok=True)
    headers = {
        "Content-Length": str(len(payload)),
        "Content-Type": str(metadata.get("artifact_media_type", "application/octet-stream")),
        "X-DFPOS-Slicer-Metadata": encoded_metadata
        if encoded_metadata is not None
        else _metadata_header(metadata, padded=padded),
    }
    if response_headers:
        headers.update(response_headers)

    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, headers=headers, content=payload)
        ),
    )
    return client.slice_artifact(model_path, workspace), workspace


def test_slice_artifact_streams_authenticated_multipart_to_workspace(tmp_path):
    payload = b"PK\x03\x04native-bambu-artifact\x00\xff"
    model_path = tmp_path / "model.stl"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    model_path.write_bytes(b"solid model\nendsolid model\n")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        request_body = request.read()
        assert request.url.path == "/api/v1/slice-artifact"
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
        assert b'name="model_file"' in request_body
        assert b'name="profile_name"' in request_body
        assert b"bambu_a1" in request_body
        assert b'name="slicer_options"' in request_body
        assert b'"material": "PLA"' in request_body
        return httpx.Response(
            200,
            headers={
                "Content-Length": str(len(payload)),
                "Content-Type": "application/vnd.bambulab.gcode-3mf",
                "X-DFPOS-Slicer-Metadata": _metadata_header(_metadata(payload)),
            },
            content=payload,
        )

    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = client.slice_artifact(
        model_file_path=model_path,
        workspace=workspace,
        profile_name="bambu_a1",
        slicer_options={"material": "PLA", "nozzle_diameter": "0.4"},
        preserve_orientation=True,
    )

    artifact_path = Path(result["artifact_path"])
    assert result["success"] is True
    assert artifact_path == workspace / "dragon.gcode.3mf"
    assert artifact_path.read_bytes() == payload
    assert len(requests) == 1


def test_slice_artifact_rejects_metadata_fields_outside_public_contract(tmp_path):
    payload = b"native artifact"
    metadata = _metadata(payload, internal_workspace="/tmp/private-engine-output")

    result, workspace = _call_artifact_client(tmp_path, metadata, payload)

    assert result["success"] is False
    assert "metadata" in result["error"].lower()
    assert list(workspace.iterdir()) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"success": False},
        {"engine_key": ["bambu"]},
        {"fallback_used": 0},
        {"filament_grams": []},
        {"layer_count": True},
        {"profile_ids": {"machine": 4}},
        {"artifact_size": "15"},
        {"artifact_sha256": "not-a-sha256"},
        {"direct_print_eligible": 1},
        {"primary_failure": {"engine_key": "bambu", "code": "timeout", "message": 9}},
    ],
)
def test_slice_artifact_rejects_wrong_metadata_schema_types(tmp_path, overrides):
    payload = b"native artifact"

    result, workspace = _call_artifact_client(tmp_path, _metadata(payload, **overrides), payload)

    assert result["success"] is False
    assert "metadata" in result["error"].lower()
    assert list(workspace.iterdir()) == []


def test_slice_artifact_returns_bounded_sanitized_json_service_error(tmp_path):
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir()
    response_body = {
        "success": False,
        "error": {
            "code": "invalid_profile\nignored",
            "message": "Unsupported profile.\x00" + "x" * 2_000,
        },
    }
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(lambda _request: httpx.Response(422, json=response_body)),
    )

    result = client.slice_artifact(model_path, workspace)

    assert result["success"] is False
    assert result["error"].startswith("invalid_profileignored: Unsupported profile.")
    assert "\x00" not in result["error"]
    assert len(result["error"]) <= 768
    assert list(workspace.iterdir()) == []


def test_slice_artifact_does_not_delete_preexisting_workspace_file(tmp_path):
    payload = b"native artifact"
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir()
    existing = workspace / "dragon.gcode.3mf"
    existing.write_bytes(b"keep this file")
    metadata = _metadata(payload)
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(payload)),
                    "Content-Type": metadata["artifact_media_type"],
                    "X-DFPOS-Slicer-Metadata": _metadata_header(metadata),
                },
                content=payload,
            )
        ),
    )

    result = client.slice_artifact(model_path, workspace)

    assert result["success"] is False
    assert existing.read_bytes() == b"keep this file"
    assert str(tmp_path) not in result["error"]
    assert len(result["error"]) <= 768


def test_slice_artifact_rejects_response_media_type_that_disagrees_with_metadata(tmp_path):
    payload = b"native artifact"
    metadata = _metadata(payload)

    result, workspace = _call_artifact_client(
        tmp_path,
        metadata,
        payload,
        response_headers={"Content-Type": "text/plain"},
    )

    assert result["success"] is False
    assert list(workspace.iterdir()) == []


@pytest.mark.parametrize("padded", [False, True])
def test_slice_artifact_accepts_padded_and_unpadded_base64url_metadata(tmp_path, padded):
    payload = b"native artifact"

    result, workspace = _call_artifact_client(
        tmp_path,
        _metadata(payload),
        payload,
        padded=padded,
    )

    assert result["success"] is True
    assert Path(result["artifact_path"]).read_bytes() == payload
    assert Path(result["artifact_path"]).parent == workspace


def test_slice_artifact_rejects_noncanonical_base64url_padding(tmp_path):
    payload = b"native artifact"
    metadata = _metadata(payload)
    malformed = _metadata_header(metadata, padded=True) + "="

    result, workspace = _call_artifact_client(
        tmp_path,
        metadata,
        payload,
        encoded_metadata=malformed,
    )

    assert result["success"] is False
    assert list(workspace.iterdir()) == []


@pytest.mark.parametrize(
    ("metadata_overrides", "response_headers"),
    [
        ({"artifact_size": 16}, None),
        ({"artifact_sha256": "0" * 64}, None),
        ({}, {"Content-Length": "16"}),
    ],
)
def test_slice_artifact_deletes_partial_file_when_size_or_sha_is_corrupt(
    tmp_path, metadata_overrides, response_headers
):
    payload = b"native artifact"
    metadata = _metadata(payload, **metadata_overrides)

    result, workspace = _call_artifact_client(
        tmp_path,
        metadata,
        payload,
        response_headers=response_headers,
    )

    assert result["success"] is False
    assert list(workspace.iterdir()) == []


@pytest.mark.parametrize("filename", ["../escape.gcode", r"C:\\escape.gcode", ".hidden"])
def test_slice_artifact_rejects_unsafe_artifact_filename_before_writing(tmp_path, filename):
    payload = b"native artifact"

    result, workspace = _call_artifact_client(
        tmp_path,
        _metadata(payload, artifact_filename=filename),
        payload,
    )

    assert result["success"] is False
    assert list(workspace.iterdir()) == []
    assert not (tmp_path / "escape.gcode").exists()


class _FailingArtifactStream(httpx.SyncByteStream):
    def __init__(self):
        self.closed = False

    def __iter__(self):
        yield b"partial artifact"
        raise httpx.ReadError("connection interrupted")

    def close(self):
        self.closed = True


class _CountingArtifactStream(httpx.SyncByteStream):
    def __init__(self, payload: bytes):
        self.payload = payload
        self.chunks_read = 0
        self.closed = False

    def __iter__(self):
        self.chunks_read += 1
        yield self.payload

    def close(self):
        self.closed = True


def test_slice_artifact_rejects_declared_size_disagreement_before_reading_body(tmp_path):
    payload = b"native artifact"
    metadata = _metadata(payload)
    stream = _CountingArtifactStream(payload)
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir()
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(payload) + 1),
                    "Content-Type": metadata["artifact_media_type"],
                    "X-DFPOS-Slicer-Metadata": _metadata_header(metadata),
                },
                stream=stream,
            )
        ),
    )

    result = client.slice_artifact(model_path, workspace)

    assert result["success"] is False
    assert stream.chunks_read == 0
    assert stream.closed is True
    assert list(workspace.iterdir()) == []


def test_slice_artifact_deletes_partial_file_and_closes_interrupted_response(tmp_path):
    payload = b"partial artifact plus expected remainder"
    metadata = _metadata(payload)
    stream = _FailingArtifactStream()
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir()
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={
                    "Content-Length": str(len(payload)),
                    "Content-Type": metadata["artifact_media_type"],
                    "X-DFPOS-Slicer-Metadata": _metadata_header(metadata),
                },
                stream=stream,
            )
        ),
    )

    result = client.slice_artifact(model_path, workspace)

    assert result["success"] is False
    assert list(workspace.iterdir()) == []
    assert stream.closed is True


class _OversizedErrorStream(httpx.SyncByteStream):
    def __init__(self):
        self.chunks_read = 0
        self.closed = False

    def __iter__(self):
        for _ in range(10_000):
            self.chunks_read += 1
            yield b"not-json" * 128

    def close(self):
        self.closed = True


def test_slice_artifact_bounds_non_json_error_reading_and_closes_response(tmp_path):
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir()
    stream = _OversizedErrorStream()
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(lambda _request: httpx.Response(503, stream=stream)),
    )

    result = client.slice_artifact(model_path, workspace)

    assert result == {"success": False, "error": "Slicer service returned HTTP 503."}
    assert stream.chunks_read <= 5
    assert stream.closed is True
    assert list(workspace.iterdir()) == []


class _FakeSlicerClient:
    def is_configured(self) -> bool:
        return True

    def slice_artifact(self, **kwargs):
        artifact_path = Path(kwargs["workspace"]) / "dragon.gcode.3mf"
        artifact_payload = b"PK\x03\x04native\x00\xff"
        artifact_path.write_bytes(artifact_payload)
        return {
            "success": True,
            "filament_grams": "12.5",
            "print_minutes": "42",
            "layer_count": 210,
            "profile_ids": {"machine": "Bambu Lab A1 0.4 nozzle"},
            "primary_failure": None,
            "artifact_path": artifact_path,
            "artifact_filename": artifact_path.name,
            "artifact_media_type": "application/vnd.bambulab.gcode-3mf",
            "artifact_size": len(artifact_payload),
            "artifact_sha256": hashlib.sha256(artifact_payload).hexdigest(),
            "engine_key": "bambu",
            "engine_name": "Bambu Studio",
            "engine_version": "2.7.1.62",
            "fallback_used": False,
            "direct_print_eligible": True,
            "estimate_only": False,
        }


def test_slice_with_slicer_returns_native_artifact_and_engine_metadata(tmp_path, monkeypatch):
    model_path = tmp_path / "model.stl"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    model_path.write_text("solid model\nendsolid model\n", encoding="utf-8")
    monkeypatch.setattr(slicer_client, "get_slicer_client", lambda: _FakeSlicerClient())

    result = slice_with_slicer(
        model_path,
        workspace=workspace,
        profile_name="bambu_a1.ini",
        slicer_options={"infill_percent": "20%"},
    )

    assert result.success is True
    assert result.filament_grams == Decimal("12.5")
    assert result.print_minutes == Decimal("42")
    assert result.artifact_path == workspace / "dragon.gcode.3mf"
    assert result.artifact_filename == "dragon.gcode.3mf"
    assert result.artifact_media_type == "application/vnd.bambulab.gcode-3mf"
    assert result.artifact_size == len(b"PK\x03\x04native\x00\xff")
    assert result.artifact_sha256 == hashlib.sha256(b"PK\x03\x04native\x00\xff").hexdigest()
    assert result.engine_key == "bambu"
    assert result.engine_name == "Bambu Studio"
    assert result.engine_version == "2.7.1.62"
    assert result.fallback_used is False
    assert result.direct_print_eligible is True
    assert result.estimate_only is False
    assert result.stats == {
        "layer_count": 210,
        "profile_ids": {"machine": "Bambu Lab A1 0.4 nozzle"},
        "primary_failure": None,
    }


def test_prusaslicer_compatibility_name_delegates_to_engine_neutral_function(tmp_path, monkeypatch):
    model_path = tmp_path / "model.stl"
    model_path.write_bytes(b"solid model\nendsolid model\n")
    sentinel = object()
    calls = []

    def fake_slice_with_slicer(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(model_analysis, "slice_with_slicer", fake_slice_with_slicer)

    result = slice_with_prusaslicer(model_path, profile_name="bambu_a1")

    assert result is sentinel
    assert calls == [
        (
            (model_path,),
            {
                "profile_name": "bambu_a1",
                "output_path": None,
                "center": "128,128",
                "slicer_options": None,
                "preserve_orientation": None,
            },
        )
    ]
