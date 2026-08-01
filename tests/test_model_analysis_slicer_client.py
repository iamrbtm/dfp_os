from __future__ import annotations

import base64
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import config as app_config
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


def _prusa_metadata(payload: bytes, **overrides):
    metadata = _metadata(
        payload,
        engine_key="prusa",
        engine_name="PrusaSlicer",
        engine_version="2.9.2",
        fallback_used=True,
        primary_failure={
            "engine_key": "bambu",
            "code": "timeout",
            "message": "Bambu Studio timed out.",
        },
        artifact_filename="dragon.gcode",
        artifact_media_type="text/x.gcode",
        direct_print_eligible=False,
        estimate_only=True,
    )
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
    workspace.mkdir(mode=0o700, exist_ok=True)
    workspace.chmod(0o700)
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
    workspace.mkdir(mode=0o700)
    model_path.write_bytes(b"solid model\nendsolid model\n")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/v1/slice-artifact"
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
        request_prefix = bytearray()
        required = (
            b'name="model_file"',
            b'name="profile_name"',
            b"bambu_a1",
            b'name="slicer_options"',
            b'"material": "PLA"',
        )
        for chunk in request.stream:
            remaining = 8192 - len(request_prefix)
            request_prefix.extend(chunk[:remaining])
            if all(value in request_prefix for value in required):
                break
            assert remaining > 0, "multipart settings were not present in the bounded prefix"
        request_body = bytes(request_prefix)
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


def test_slice_artifact_accepts_semantically_consistent_prusa_fallback(tmp_path):
    payload = b"; PrusaSlicer native G-code\nG1 X1 Y1\n"

    result, workspace = _call_artifact_client(tmp_path, _prusa_metadata(payload), payload)

    assert result["success"] is True
    assert result["engine_key"] == "prusa"
    assert result["fallback_used"] is True
    assert result["estimate_only"] is True
    assert result["direct_print_eligible"] is False
    assert Path(result["artifact_path"]) == workspace / "dragon.gcode"


@pytest.mark.parametrize(
    "metadata",
    [
        lambda payload: _metadata(payload, engine_key="orca", engine_name="OrcaSlicer"),
        lambda payload: _metadata(payload, engine_name="BambuStudio"),
        lambda payload: _metadata(payload, engine_version="unknown"),
        lambda payload: _metadata(payload, artifact_filename="dragon.gcode"),
        lambda payload: _metadata(payload, artifact_media_type="text/x.gcode"),
        lambda payload: _metadata(payload, direct_print_eligible=False),
        lambda payload: _metadata(payload, estimate_only=True),
        lambda payload: _metadata(payload, fallback_used=True),
        lambda payload: _metadata(
            payload,
            primary_failure={
                "engine_key": "bambu",
                "code": "timeout",
                "message": "Bambu Studio timed out.",
            },
        ),
        lambda payload: _prusa_metadata(payload, fallback_used=False),
        lambda payload: _prusa_metadata(payload, primary_failure=None),
        lambda payload: _prusa_metadata(payload, artifact_filename="dragon.gcode.3mf"),
        lambda payload: _prusa_metadata(
            payload,
            artifact_media_type="application/vnd.bambulab.gcode-3mf",
        ),
        lambda payload: _prusa_metadata(payload, direct_print_eligible=True),
        lambda payload: _prusa_metadata(payload, estimate_only=False),
        lambda payload: _prusa_metadata(
            payload,
            primary_failure={
                "engine_key": "prusa",
                "code": "timeout",
                "message": "PrusaSlicer timed out.",
            },
        ),
        lambda payload: _prusa_metadata(
            payload,
            primary_failure={
                "engine_key": "bambu",
                "code": "arbitrary_internal_code",
                "message": "private failure",
            },
        ),
        lambda payload: _prusa_metadata(
            payload,
            primary_failure={
                "engine_key": "bambu",
                "code": "timeout",
                "message": "Bambu Studio execution failed.",
            },
        ),
    ],
)
def test_slice_artifact_rejects_impossible_engine_artifact_semantics(tmp_path, metadata):
    payload = b"native artifact"

    result, workspace = _call_artifact_client(tmp_path, metadata(payload), payload)

    assert result["success"] is False
    assert "metadata" in result["error"].lower()
    assert list(workspace.iterdir()) == []


def test_slice_artifact_returns_bounded_sanitized_json_service_error(tmp_path):
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
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
    workspace.mkdir(mode=0o700)
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


def test_slice_artifact_rejects_symlink_workspace_without_touching_target(tmp_path):
    model_path = tmp_path / "source.stl"
    target = tmp_path / "real-workspace"
    workspace_link = tmp_path / "workspace-link"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    target.mkdir(mode=0o700)
    workspace_link.symlink_to(target, target_is_directory=True)
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("workspace validation must precede the HTTP request")
        ),
    )

    result = client.slice_artifact(model_path, workspace_link)

    assert result["success"] is False
    assert "workspace" in result["error"].lower()
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("mode", [0o750, 0o707, 0o777])
def test_slice_artifact_rejects_workspace_without_exact_private_mode(tmp_path, mode):
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=mode)
    workspace.chmod(mode)
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("workspace mode validation must precede HTTP")
        ),
    )

    result = client.slice_artifact(model_path, workspace)

    assert result["success"] is False
    assert "0700" in result["error"]
    assert list(workspace.iterdir()) == []


def test_slice_artifact_rejects_workspace_not_owned_by_effective_user(tmp_path, monkeypatch):
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
    real_lstat = os.lstat

    def foreign_owned_lstat(path):
        result = real_lstat(path)
        if Path(path) != workspace:
            return result
        return SimpleNamespace(
            st_mode=result.st_mode,
            st_dev=result.st_dev,
            st_ino=result.st_ino,
            st_uid=os.geteuid() + 1,
        )

    monkeypatch.setattr(slicer_client.os, "lstat", foreign_owned_lstat)
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("workspace ownership validation must precede HTTP")
        ),
    )

    result = client.slice_artifact(model_path, workspace)

    assert result["success"] is False
    assert "effective user" in result["error"].lower()
    assert list(workspace.iterdir()) == []


def test_slice_artifact_directory_swap_cleans_only_original_fd_relative_file(tmp_path, monkeypatch):
    payload = b"native artifact"
    metadata = _metadata(payload)
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    original_after_swap = tmp_path / "original-workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
    unlink_calls = []
    real_unlink = os.unlink

    def tracking_unlink(path, *, dir_fd=None):
        unlink_calls.append((path, dir_fd))
        if dir_fd is None:
            return real_unlink(path)
        return real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(slicer_client.os, "unlink", tracking_unlink)

    def handler(_request):
        workspace.rename(original_after_swap)
        workspace.mkdir(mode=0o700)
        (workspace / "replacement-marker").write_bytes(b"do not touch")
        return httpx.Response(
            200,
            headers={
                "Content-Length": str(len(payload)),
                "Content-Type": metadata["artifact_media_type"],
                "X-DFPOS-Slicer-Metadata": _metadata_header(metadata),
            },
            content=payload,
        )

    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = client.slice_artifact(model_path, workspace)

    assert result["success"] is False
    assert (workspace / "replacement-marker").exists()
    assert (workspace / "replacement-marker").read_bytes() == b"do not touch"
    assert not (workspace / "dragon.gcode.3mf").exists()
    assert not (original_after_swap / "dragon.gcode.3mf").exists()
    assert any(path == "dragon.gcode.3mf" and dir_fd is not None for path, dir_fd in unlink_calls)


def test_slice_artifact_caller_keeps_workspace_stable_until_artifact_is_consumed(tmp_path):
    payload = b"native artifact"
    metadata = _metadata(payload)
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    moved_workspace = tmp_path / "moved-workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
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

    assert result["success"] is True
    workspace.rename(moved_workspace)
    workspace.mkdir(mode=0o700)
    # The returned path is intentionally path-based. A same-UID caller replacing
    # its workspace after return is outside the client's exclusive-owner contract.
    assert not Path(result["artifact_path"]).exists()
    assert (moved_workspace / "dragon.gcode.3mf").read_bytes() == payload


def test_slice_artifact_closes_created_descriptor_when_fdopen_fails(tmp_path, monkeypatch):
    payload = b"native artifact"
    metadata = _metadata(payload)
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
    artifact_descriptors = []
    real_open = os.open

    def tracking_open(path, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is None:
            return real_open(path, flags, mode)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        artifact_descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(slicer_client.os, "open", tracking_open)
    monkeypatch.setattr(
        slicer_client.os,
        "fdopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("fdopen failed")),
    )
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
    assert len(artifact_descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(artifact_descriptors[0])
    assert list(workspace.iterdir()) == []


def test_slice_artifact_closes_workspace_descriptor_when_initial_fstat_fails(tmp_path, monkeypatch):
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
    unrelated = workspace / "keep.txt"
    unrelated.write_bytes(b"keep")
    opened_descriptors = []
    real_open = os.open
    real_fstat = os.fstat

    def tracking_open(path, flags, mode=0o777, *, dir_fd=None):
        descriptor = (
            real_open(path, flags, mode)
            if dir_fd is None
            else real_open(path, flags, mode, dir_fd=dir_fd)
        )
        opened_descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(slicer_client.os, "open", tracking_open)
    monkeypatch.setattr(
        slicer_client.os,
        "fstat",
        lambda _descriptor: (_ for _ in ()).throw(OSError("workspace fstat failed")),
    )
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("workspace fstat must precede the HTTP request")
        ),
    )

    result = client.slice_artifact(model_path, workspace)

    assert result["success"] is False
    assert len(opened_descriptors) == 1
    with pytest.raises(OSError):
        real_fstat(opened_descriptors[0])
    assert unrelated.read_bytes() == b"keep"


def test_slice_artifact_closes_and_unlinks_when_artifact_fstat_fails(tmp_path, monkeypatch):
    payload = b"native artifact"
    metadata = _metadata(payload)
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
    unrelated = workspace / "keep.txt"
    unrelated.write_bytes(b"keep")
    artifact_descriptors = []
    real_open = os.open
    real_fstat = os.fstat

    def tracking_open(path, flags, mode=0o777, *, dir_fd=None):
        descriptor = (
            real_open(path, flags, mode)
            if dir_fd is None
            else real_open(path, flags, mode, dir_fd=dir_fd)
        )
        if dir_fd is not None:
            artifact_descriptors.append(descriptor)
        return descriptor

    def fail_artifact_fstat(descriptor):
        if descriptor in artifact_descriptors:
            raise OSError("artifact fstat failed")
        return real_fstat(descriptor)

    monkeypatch.setattr(slicer_client.os, "open", tracking_open)
    monkeypatch.setattr(slicer_client.os, "fstat", fail_artifact_fstat)
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
    assert len(artifact_descriptors) == 1
    with pytest.raises(OSError):
        real_fstat(artifact_descriptors[0])
    assert not (workspace / "dragon.gcode.3mf").exists()
    assert unrelated.read_bytes() == b"keep"


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


def test_slice_artifact_rejects_noncanonical_base64url_pad_bits(tmp_path):
    payload = b"native artifact"
    metadata = _metadata(payload, layer_count=21)
    canonical = _metadata_header(metadata)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    assert len(canonical) % 4 in {2, 3}
    last_index = alphabet.index(canonical[-1])
    noncanonical = canonical[:-1] + alphabet[last_index + 1]
    assert base64.urlsafe_b64decode(
        noncanonical + "=" * (-len(noncanonical) % 4)
    ) == base64.urlsafe_b64decode(canonical + "=" * (-len(canonical) % 4))

    result, workspace = _call_artifact_client(
        tmp_path,
        metadata,
        payload,
        encoded_metadata=noncanonical,
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


class _SuccessfulMultiChunkStream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.chunks_yielded = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.chunks_yielded += 1
            yield chunk

    def close(self):
        self.closed = True


def test_slice_artifact_writes_successful_response_incrementally(tmp_path, monkeypatch):
    chunks = [b"a" * (1024 * 1024), b"b" * (1024 * 1024), b"c" * (1024 * 1024)]
    payload = b"".join(chunks)
    metadata = _metadata(payload)
    stream = _SuccessfulMultiChunkStream(chunks)
    write_observations = []
    real_fdopen = os.fdopen

    class ObservedFile:
        def __init__(self, descriptor, mode):
            self.file = real_fdopen(descriptor, mode)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

        def write(self, data):
            write_observations.append(stream.chunks_yielded)
            return self.file.write(data)

    monkeypatch.setattr(slicer_client.os, "fdopen", ObservedFile)
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
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

    assert result["success"] is True
    assert write_observations == [1, 2, 3]
    assert stream.closed is True
    assert Path(result["artifact_path"]).read_bytes() == payload


def test_slice_artifact_rejects_declared_size_disagreement_before_reading_body(tmp_path):
    payload = b"native artifact"
    metadata = _metadata(payload)
    stream = _CountingArtifactStream(payload)
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
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


def test_slicer_artifact_size_config_defaults_to_512_mib_and_requires_positive_integer():
    assert getattr(app_config.Config, "SLICER_ARTIFACT_MAX_BYTES", None) == 512 * 1024 * 1024
    positive_int = getattr(app_config, "_positive_int", None)
    assert positive_int is not None
    assert positive_int("1", "TEST_LIMIT") == 1
    with pytest.raises(ValueError, match="TEST_LIMIT must be a positive integer"):
        positive_int("0", "TEST_LIMIT")
    with pytest.raises(ValueError, match="TEST_LIMIT must be a positive integer"):
        positive_int("not-an-integer", "TEST_LIMIT")


def test_slice_artifact_rejects_consistent_oversized_response_before_reading_body(tmp_path):
    payload = b"native artifact"
    metadata = _metadata(payload)
    stream = _CountingArtifactStream(payload)
    model_path = tmp_path / "source.stl"
    workspace = tmp_path / "workspace"
    model_path.write_bytes(b"solid source\nendsolid source\n")
    workspace.mkdir(mode=0o700)
    client = slicer_client.SlicerClient(
        base_url="http://slicer.test",
        token="secret-token",
        max_artifact_bytes=len(payload) - 1,
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
    assert "configured size limit" in result["error"].lower()
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
    workspace.mkdir(mode=0o700)
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
    workspace.mkdir(mode=0o700)
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
    workspace.mkdir(mode=0o700)
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
