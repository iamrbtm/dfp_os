from __future__ import annotations

import base64
import asyncio
import concurrent.futures
import json
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from starlette.requests import Request

from app.api.auth import _authorize_request
from app.config import settings
from app.main import create_app
from app.services.engines.base import EngineArtifact, RequestValidationError
from app.services.engines.orchestrator import OrchestratedFailure, OrchestratedResult

_TOKEN = "test-slicer-token-0123456789abcdef"


@dataclass
class _Runtime:
    orchestrator: object
    engines: dict[str, object]
    admission: object = field(default_factory=lambda: _UnlimitedAdmission())
    jobs: object | None = None
    cleanup: object = field(default_factory=lambda: _ImmediateCleanupManager())

    def __post_init__(self) -> None:
        if self.jobs is None:
            self.jobs = _ImmediateJobs(self.admission)


class _UnlimitedAdmission:
    async def try_acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


class _ImmediateCleanupManager:
    async def cleanup(self, workspace: Path) -> None:
        try:
            shutil.rmtree(workspace)
        except FileNotFoundError:
            pass

    async def shutdown(self) -> None:
        return None


class _ImmediateLease:
    def __init__(self, admission: object) -> None:
        self._admission = admission

    async def run(self, function, *args, **kwargs):
        return function(*args, **kwargs)

    async def release(self) -> None:
        await self._admission.release()


class _ImmediateJobs:
    def __init__(self, admission: object) -> None:
        self.admission = admission

    async def try_acquire(self):
        if not await self.admission.try_acquire():
            return None
        return _ImmediateLease(self.admission)


class _FakeOrchestrator:
    def __init__(self, outcome: OrchestratedResult | BaseException) -> None:
        self.outcome = outcome
        self.calls: list[tuple[Path, Path, object]] = []

    def slice(self, model_path: Path, workspace: Path, options: object) -> OrchestratedResult:
        self.calls.append((model_path, workspace, options))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        if self.outcome.artifact is not None:
            artifact_path = workspace / "engine-output.bin"
            artifact_path.write_bytes(b"native slicer artifact")
            artifact = EngineArtifact(
                **{
                    **self.outcome.artifact.__dict__,
                    "artifact_path": artifact_path,
                    "artifact_size": artifact_path.stat().st_size,
                }
            )
            return OrchestratedResult(
                artifact=artifact,
                fallback_used=self.outcome.fallback_used,
                primary_failure=self.outcome.primary_failure,
                failures=self.outcome.failures,
            )
        return self.outcome


def _override_runtime(app, runtime: _Runtime) -> None:
    from app.api.dependencies import get_slicer_runtime

    async def runtime_override():
        return runtime

    app.dependency_overrides[get_slicer_runtime] = runtime_override


def _artifact(tmp_path: Path, *, filename: str = "dragon.gcode.3mf") -> EngineArtifact:
    return EngineArtifact(
        engine_key="bambu",
        engine_name="Bambu Studio",
        engine_version="2.7.1.62",
        artifact_path=tmp_path / filename,
        artifact_filename=filename,
        artifact_media_type="application/vnd.bambulab.gcode-3mf",
        artifact_size=0,
        artifact_sha256="a" * 64,
        filament_grams=Decimal("12.50"),
        print_minutes=Decimal("95.25"),
        layer_count=221,
        profile_ids={
            "machine": "Bambu Lab A1 0.4 nozzle",
            "process": "0.20mm Standard @BBL A1",
            "filament": "Generic PLA @BBL A1",
        },
        direct_print_eligible=True,
        estimate_only=False,
        diagnostics={"stderr": "/private/workspace must not escape"},
    )


def _success(tmp_path: Path, *, fallback: bool = False) -> OrchestratedResult:
    primary_failure = OrchestratedFailure("bambu", "timeout", "Bambu Studio timed out.") if fallback else None
    return OrchestratedResult(
        artifact=_artifact(tmp_path),
        fallback_used=fallback,
        primary_failure=primary_failure,
        failures=(primary_failure,) if primary_failure else (),
    )


@pytest.fixture
async def authorized_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "internal_api_token", _TOKEN)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield app, client


_NATIVE_FILE_RESPONSE_SANDBOX_TESTS = frozenset(
    {
        "test_auth_uses_constant_time_token_comparison",
        "test_slice_artifact_streams_native_bytes_and_compact_public_metadata",
        "test_live_endpoint_remains_responsive_while_slice_is_offloaded",
        "test_concurrent_slice_limit_returns_stable_busy_response",
        "test_slice_artifact_reads_only_bounded_one_mib_chunks",
    }
)


@pytest.fixture(autouse=True)
def local_file_response_io(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Patch only AnyIO's broken worker-thread file boundary in this Python 3.14 sandbox."""

    if request.node.name not in _NATIVE_FILE_RESPONSE_SANDBOX_TESTS:
        return

    class LocalAsyncFile:
        def __init__(self, path: str | Path) -> None:
            self._file = Path(path).open("rb")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self._file.close()

        async def read(self, size: int = -1) -> bytes:
            return self._file.read(size)

        async def seek(self, offset: int) -> int:
            return self._file.seek(offset)

    async def open_file(path, *_args, **_kwargs):
        return LocalAsyncFile(path)

    monkeypatch.setattr("starlette.responses.anyio.open_file", open_file)


async def _post(client: httpx.AsyncClient, *, token: str | None = _TOKEN, content: bytes = b"solid cube"):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return await client.post(
        "/api/v1/slice-artifact",
        headers=headers,
        files={"model_file": (r"C:\private\dragon.stl", content, "application/octet-stream")},
        data={
            "profile_name": "bambu_a1",
            "preserve_orientation": "true",
            "slicer_options": json.dumps({"material": "PLA", "nozzle_diameter": "0.4"}),
        },
    )


@pytest.mark.parametrize("token", [None, "", "incorrect"])
async def test_auth_rejects_before_runtime_or_upload_reader_runs(
    authorized_client, monkeypatch: pytest.MonkeyPatch, token: str | None
):
    app, client = authorized_client

    def forbidden_runtime():
        raise AssertionError("authentication must run before engine construction")

    from app.api.dependencies import get_slicer_runtime

    app.dependency_overrides[get_slicer_runtime] = forbidden_runtime

    async def forbidden_copy(*_args, **_kwargs):
        raise AssertionError("authentication must run before the upload is copied")

    monkeypatch.setattr("app.api.routes.slice._copy_upload", forbidden_copy)

    response = await _post(client, token=token)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


async def test_auth_uses_constant_time_token_comparison(
    authorized_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    comparisons: list[tuple[str, str]] = []

    def fake_compare_digest(left: str, right: str) -> bool:
        comparisons.append((left, right))
        return left == right

    monkeypatch.setattr("app.api.auth.secrets.compare_digest", fake_compare_digest)
    _override_runtime(app, _Runtime(orchestrator, {}))

    response = await _post(client)

    assert response.status_code == 200
    assert comparisons == [(_TOKEN, _TOKEN)]


@pytest.mark.parametrize(
    "configured_token",
    [
        "",
        "too-short",
        "change-me-slicer-token",
        "replace-with-a-random-32-byte-token",
        "configured-token-with-control\x00",
        "nön-ascii-configured-token-123456",
    ],
)
async def test_auth_fails_closed_when_configured_token_is_invalid(
    authorized_client, monkeypatch: pytest.MonkeyPatch, configured_token: str
):
    _app, client = authorized_client
    monkeypatch.setattr(settings, "internal_api_token", configured_token)

    response = await _post(client, token=_TOKEN)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


@pytest.mark.parametrize("raw_token", [b"token-with-control\x00value", b"non-ascii-\xff-token"])
def test_auth_rejects_malformed_provided_token_without_compare_digest_error(raw_token: bytes):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/slice-artifact",
            "headers": [(b"authorization", b"Bearer " + raw_token)],
        }
    )

    with pytest.raises(Exception) as caught:
        _authorize_request(request)

    assert getattr(caught.value, "status_code", None) == 401


async def test_preparser_receive_wrapper_rejects_cumulative_body_bytes():
    from app.api.auth import RequestBodyTooLarge, bounded_receive

    messages = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"45", "more_body": False},
        ]
    )

    async def receive():
        return next(messages)

    guarded_receive = bounded_receive(receive, limit=4)

    assert await guarded_receive() == {"type": "http.request", "body": b"123", "more_body": True}
    with pytest.raises(RequestBodyTooLarge):
        await guarded_receive()


async def test_content_length_over_total_request_budget_is_rejected_before_body_parse(
    authorized_client, monkeypatch: pytest.MonkeyPatch
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(AssertionError("engine must not run"))
    _override_runtime(app, _Runtime(orchestrator, {}))
    monkeypatch.setattr(settings, "max_model_bytes", 4)

    response = await client.post(
        "/api/v1/slice-artifact",
        headers={
            "Authorization": f"Bearer {_TOKEN}",
            "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": "70000",
        },
        content=b"",
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert orchestrator.calls == []


async def test_extra_multipart_files_cannot_exceed_total_request_budget(
    authorized_client, monkeypatch: pytest.MonkeyPatch
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(AssertionError("engine must not run"))
    _override_runtime(app, _Runtime(orchestrator, {}))
    monkeypatch.setattr(settings, "max_model_bytes", 4)
    files = [("model_file", ("model.stl", b"1234", "application/octet-stream"))]
    files.extend(("extra", (f"extra-{index}.bin", b"x" * 1024, "application/octet-stream")) for index in range(70))

    response = await client.post(
        "/api/v1/slice-artifact",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        files=files,
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert orchestrator.calls == []


def _multipart_body(boundary: str, parts: list[tuple[str, str | None, bytes]]) -> bytes:
    body = bytearray()
    for name, filename, value in parts:
        body.extend(f"--{boundary}\r\n".encode())
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        body.extend(f"{disposition}\r\n\r\n".encode())
        body.extend(value)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body)


@pytest.fixture
def tracked_spooled_files(monkeypatch: pytest.MonkeyPatch):
    created = []
    original = tempfile.SpooledTemporaryFile

    def tracked(*args, **kwargs):
        spool = original(*args, **kwargs)
        created.append(spool)
        return spool

    monkeypatch.setattr("starlette.formparsers.SpooledTemporaryFile", tracked)
    return created


def _streaming_request(boundary: str, chunks: list[bytes]) -> Request:
    messages = iter(
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    )

    async def receive():
        return next(messages)

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/slice-artifact",
            "headers": [(b"content-type", f'multipart/form-data; boundary="{boundary}"'.encode())],
        },
        receive,
    )


async def test_multipart_preparse_handles_split_quoted_boundary_and_headers():
    from app.api.auth import preparse_slice_multipart

    boundary = "quoted-boundary-123"
    body = _multipart_body(
        boundary,
        [
            ("model_file", "dragon.stl", b"solid"),
            ("profile_name", None, b"bambu_a1"),
        ],
    )
    messages = iter(
        {"type": "http.request", "body": bytes([byte]), "more_body": index < len(body) - 1}
        for index, byte in enumerate(body)
    )

    async def receive():
        return next(messages)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/slice-artifact",
            "headers": [(b"content-type", f'multipart/form-data; boundary="{boundary}"'.encode())],
        },
        receive,
    )

    await preparse_slice_multipart(request)

    form = await request.form()
    assert form["model_file"].filename == "dragon.stl"
    assert form["profile_name"] == "bambu_a1"


async def test_multipart_malformed_after_file_creation_closes_parser_owned_spool(tracked_spooled_files):
    from app.api.auth import MalformedMultipart, preparse_slice_multipart

    boundary = "malformed-after-file"
    valid_file = _multipart_body(boundary, [("model_file", "dragon.stl", b"solid")])
    malformed = valid_file.removesuffix(f"--{boundary}--\r\n".encode()) + (
        f"--{boundary}\r\nMalformed Header\r\n\r\nvalue\r\n--{boundary}--\r\n".encode()
    )
    request = _streaming_request(boundary, [malformed])

    with pytest.raises(MalformedMultipart):
        await preparse_slice_multipart(request)

    assert tracked_spooled_files
    assert all(spool.closed for spool in tracked_spooled_files)


async def test_multipart_later_body_limit_closes_parser_owned_spool(tracked_spooled_files):
    from app.api.auth import RequestBodyTooLarge, bounded_receive, preparse_slice_multipart

    boundary = "later-over-limit"
    first = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="model_file"; filename="dragon.stl"\r\n\r\n'.encode()
        + b"small"
    )
    request = _streaming_request(boundary, [first, b"x" * 64])
    request._receive = bounded_receive(request.receive, limit=len(first) + 1)

    with pytest.raises(RequestBodyTooLarge):
        await preparse_slice_multipart(request)

    assert tracked_spooled_files
    assert all(spool.closed for spool in tracked_spooled_files)


async def test_unexpected_parser_failure_closes_owned_spool(monkeypatch: pytest.MonkeyPatch, tracked_spooled_files):
    from app.api.auth import _SliceMultipartParser, preparse_slice_multipart

    boundary = "unexpected-parser-error"
    body = _multipart_body(boundary, [("model_file", "dragon.stl", b"solid")])
    original = _SliceMultipartParser.on_part_data

    def fail_after_data(self, data, start, end):
        original(self, data, start, end)
        raise RuntimeError("parser internals failed")

    monkeypatch.setattr(_SliceMultipartParser, "on_part_data", fail_after_data)

    with pytest.raises(RuntimeError, match="parser internals failed"):
        await preparse_slice_multipart(_streaming_request(boundary, [body]))

    assert tracked_spooled_files
    assert all(spool.closed for spool in tracked_spooled_files)


async def test_parser_cancellation_closes_owned_spool(tracked_spooled_files):
    from app.api.auth import preparse_slice_multipart

    boundary = "cancel-parser"
    first = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="model_file"; filename="dragon.stl"\r\n\r\n'.encode()
        + b"partial"
    )
    continue_reading = asyncio.Event()
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": first, "more_body": True}
        await continue_reading.wait()
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/slice-artifact",
            "headers": [(b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
        },
        receive,
    )
    parse_task = asyncio.create_task(preparse_slice_multipart(request))
    for _ in range(100):
        if tracked_spooled_files:
            break
        await asyncio.sleep(0.01)
    parse_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await parse_task
    assert tracked_spooled_files
    assert all(spool.closed for spool in tracked_spooled_files)


@pytest.mark.parametrize(
    "parts",
    [
        [
            ("model_file", "one.stl", b"one"),
            ("model_file", "two.stl", b"two"),
        ],
        [
            ("model_file", "one.stl", b"one"),
            ("support_file", "support.stl", b"support"),
        ],
    ],
)
async def test_multipart_preparse_rejects_duplicate_or_extra_file_before_route(
    authorized_client, parts: list[tuple[str, str | None, bytes]]
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(AssertionError("engine must not run"))
    _override_runtime(app, _Runtime(orchestrator, {}))

    response = await client.post(
        "/api/v1/slice-artifact",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        files=[(name, (filename, value, "application/octet-stream")) for name, filename, value in parts],
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "malformed_request"
    assert orchestrator.calls == []


async def test_multipart_preparse_rejects_excess_fields_before_route(authorized_client):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(AssertionError("engine must not run"))
    _override_runtime(app, _Runtime(orchestrator, {}))

    response = await client.post(
        "/api/v1/slice-artifact",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        files={"model_file": ("dragon.stl", b"solid", "application/octet-stream")},
        data={f"field_{index}": "value" for index in range(5)},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_many_parts"
    assert orchestrator.calls == []


async def test_split_oversized_multipart_header_returns_413_and_closes_prior_file(
    authorized_client, tracked_spooled_files
):
    from app.api.auth import MAX_MULTIPART_HEADER_BYTES

    app, client = authorized_client
    orchestrator = _FakeOrchestrator(AssertionError("engine must not run"))
    _override_runtime(app, _Runtime(orchestrator, {}))
    boundary = "oversized-quoted-header"
    body = (
        _multipart_body(boundary, [("model_file", "dragon.stl", b"solid")]).removesuffix(f"--{boundary}--\r\n".encode())
        + f'--{boundary}\r\nX-Custom: "'.encode()
        + b"a" * (MAX_MULTIPART_HEADER_BYTES + 1)
        + f'"\r\nContent-Disposition: form-data; name="profile_name"\r\n\r\nbambu_a1\r\n--{boundary}--\r\n'.encode()
    )

    async def split_content():
        for offset in range(0, len(body), 7):
            yield body[offset : offset + 7]

    response = await client.post(
        "/api/v1/slice-artifact",
        headers={
            "Authorization": f"Bearer {_TOKEN}",
            "Content-Type": f'multipart/form-data; boundary="{boundary}"',
        },
        content=split_content(),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "multipart_headers_too_large"
    assert tracked_spooled_files
    assert all(spool.closed for spool in tracked_spooled_files)
    assert orchestrator.calls == []


async def test_unexpected_preparser_error_returns_sanitized_503_and_closes_files(
    authorized_client, monkeypatch: pytest.MonkeyPatch, tracked_spooled_files
):
    from app.api.auth import _SliceMultipartParser

    app, client = authorized_client
    orchestrator = _FakeOrchestrator(AssertionError("engine must not run"))
    _override_runtime(app, _Runtime(orchestrator, {}))
    original = _SliceMultipartParser.on_part_data

    def fail_after_data(self, data, start, end):
        original(self, data, start, end)
        if self._current_part.file is not None:
            raise RuntimeError("private parser failure /tmp/customer-model")

    monkeypatch.setattr(_SliceMultipartParser, "on_part_data", fail_after_data)
    boundary = "unexpected-integration"
    response = await client.post(
        "/api/v1/slice-artifact",
        headers={
            "Authorization": f"Bearer {_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        content=_multipart_body(boundary, [("model_file", "dragon.stl", b"solid")]),
    )

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "error": {
            "code": "request_parse_failed",
            "message": "The slicer request could not be processed.",
        },
    }
    assert "/tmp/customer-model" not in response.text
    assert tracked_spooled_files
    assert all(spool.closed for spool in tracked_spooled_files)
    assert orchestrator.calls == []


async def test_fastapi_validation_failure_closes_cached_form_upload(authorized_client, tracked_spooled_files):
    _app, client = authorized_client

    response = await client.post(
        "/api/v1/slice-artifact",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        files={"model_file": ("dragon.stl", b"solid", "application/octet-stream")},
        data={"preserve_orientation": "not-a-boolean"},
    )

    assert response.status_code == 422
    assert tracked_spooled_files
    assert all(spool.closed for spool in tracked_spooled_files)


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"data": {"profile_name": "bambu_a1"}},
        {
            "files": {"model_file": ("dragon.stl", b"solid", "application/octet-stream")},
            "data": {"preserve_orientation": "not-a-boolean"},
        },
        {
            "content": b'--broken\r\nContent-Disposition: form-data; name="model_file"\r\n\r\nsolid',
            "headers": {"Content-Type": "multipart/form-data; boundary=broken"},
        },
    ],
)
async def test_authenticated_request_validation_failures_are_structured(
    authorized_client, request_kwargs: dict[str, object]
):
    _app, client = authorized_client
    headers = {"Authorization": f"Bearer {_TOKEN}", **request_kwargs.pop("headers", {})}

    response = await client.post("/api/v1/slice-artifact", headers=headers, **request_kwargs)

    assert response.status_code == 422
    assert response.json() == {
        "success": False,
        "error": {"code": "malformed_request", "message": "The slicer request is malformed."},
    }


async def test_slice_artifact_streams_native_bytes_and_compact_public_metadata(authorized_client, tmp_path: Path):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    _override_runtime(app, _Runtime(orchestrator, {}))

    response = await _post(client)

    assert response.status_code == 200
    assert response.content == b"native slicer artifact"
    assert response.headers["content-type"] == "application/vnd.bambulab.gcode-3mf"
    assert response.headers["content-disposition"] == 'attachment; filename="dragon.gcode.3mf"'
    encoded = response.headers["X-DFPOS-Slicer-Metadata"]
    decoded = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert len(encoded.encode("ascii")) < 6144
    assert decoded == {
        "success": True,
        "engine_key": "bambu",
        "engine_name": "Bambu Studio",
        "engine_version": "2.7.1.62",
        "fallback_used": False,
        "primary_failure": None,
        "filament_grams": "12.50",
        "print_minutes": "95.25",
        "layer_count": 221,
        "profile_ids": {
            "machine": "Bambu Lab A1 0.4 nozzle",
            "process": "0.20mm Standard @BBL A1",
            "filament": "Generic PLA @BBL A1",
        },
        "artifact_filename": "dragon.gcode.3mf",
        "artifact_media_type": "application/vnd.bambulab.gcode-3mf",
        "artifact_size": len(b"native slicer artifact"),
        "artifact_sha256": "a" * 64,
        "direct_print_eligible": True,
        "estimate_only": False,
    }
    assert "diagnostics" not in decoded
    assert "private" not in encoded
    assert orchestrator.calls[0][0].name == "dragon.stl"
    assert not orchestrator.calls[0][1].exists(), "FileResponse background cleanup must remove the request workspace"


@pytest.mark.parametrize(("range_header", "expected_status"), [("nope", 400), ("bytes=99-100", 416)])
async def test_range_failures_remove_request_workspace(
    authorized_client, tmp_path: Path, range_header: str, expected_status: int
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    _override_runtime(app, _Runtime(orchestrator, {}))

    response = await client.post(
        "/api/v1/slice-artifact",
        headers={"Authorization": f"Bearer {_TOKEN}", "Range": range_header},
        files={"model_file": ("dragon.stl", b"solid", "application/octet-stream")},
    )

    assert response.status_code == expected_status
    assert not orchestrator.calls[0][1].exists()


async def test_cleanup_file_response_removes_workspace_when_send_raises(tmp_path: Path):
    from app.api.routes.slice import CleanupFileResponse

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = workspace / "artifact.bin"
    artifact.write_bytes(b"artifact")
    response = CleanupFileResponse(
        artifact,
        workspace=workspace,
        cleanup_manager=_ImmediateCleanupManager(),
        stat_result=artifact.stat(),
    )

    async def receive():
        return {"type": "http.disconnect"}

    async def failing_send(_message):
        raise OSError("client disconnected")

    with pytest.raises(OSError, match="client disconnected"):
        await response(
            {"type": "http", "method": "GET", "path": "/", "headers": []},
            receive,
            failing_send,
        )

    assert not workspace.exists()


async def test_cleanup_file_response_removes_workspace_when_stat_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from app.api.routes.slice import CleanupFileResponse

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = workspace / "artifact.bin"
    artifact.write_bytes(b"artifact")
    response = CleanupFileResponse(artifact, workspace=workspace, cleanup_manager=_ImmediateCleanupManager())

    async def fail_stat(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("starlette.responses.anyio.to_thread.run_sync", fail_stat)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    with pytest.raises(RuntimeError, match="does not exist"):
        await response(
            {"type": "http", "method": "GET", "path": "/", "headers": []},
            receive,
            send,
        )

    assert not workspace.exists()


@pytest.mark.parametrize("close_error", [RuntimeError("close failed"), asyncio.CancelledError()])
async def test_upload_close_failure_or_cancellation_still_removes_workspace(tmp_path: Path, close_error: BaseException):
    from app.api.routes.slice import slice_artifact_endpoint

    class FailingCloseUpload:
        filename = "dragon.stl"

        def __init__(self) -> None:
            self._chunks = iter([b"solid", b""])

        async def read(self, _size: int) -> bytes:
            return next(self._chunks)

        async def close(self) -> None:
            raise close_error

    orchestrator = _FakeOrchestrator(_success(tmp_path))
    runtime = _Runtime(orchestrator, {})

    with pytest.raises(type(close_error)):
        await slice_artifact_endpoint(
            model_file=FailingCloseUpload(),
            profile_name="bambu_a1",
            center="128,128",
            preserve_orientation=True,
            slicer_options=json.dumps({"material": "PLA", "nozzle_diameter": "0.4"}),
            runtime=runtime,
        )

    assert not orchestrator.calls[0][1].exists()


async def test_metadata_over_configured_cap_fails_before_response_and_removes_workspace(
    authorized_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    request_workspace = tmp_path / "request-owned"
    _override_runtime(app, _Runtime(orchestrator, {}))
    monkeypatch.setattr(settings, "metadata_header_max_bytes", 1)
    monkeypatch.setattr("app.api.routes.slice.tempfile.mkdtemp", lambda **_kwargs: str(request_workspace))

    response = await _post(client)

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "error": {
            "code": "metadata_too_large",
            "message": "The slicer result metadata exceeds the configured response limit.",
        },
    }
    assert not request_workspace.exists()


async def test_live_endpoint_remains_responsive_while_slice_is_offloaded(authorized_client, tmp_path: Path):
    from app.api.dependencies import SliceAdmission, SliceJobManager

    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    original_slice = orchestrator.slice
    entered = threading.Event()
    release = threading.Event()

    def blocked_slice(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original_slice(*args, **kwargs)

    orchestrator.slice = blocked_slice
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    jobs = SliceJobManager(SliceAdmission(1), executor=pool)
    runtime = _Runtime(orchestrator, {}, admission=jobs.admission, jobs=jobs)
    _override_runtime(app, runtime)

    slice_request = asyncio.create_task(_post(client))
    await _wait_for_thread_event(entered)
    live = await asyncio.wait_for(client.get("/health/live"), timeout=1)
    release.set()
    sliced = await asyncio.wait_for(slice_request, timeout=2)
    pool.shutdown(wait=True)

    assert live.status_code == 200
    assert live.json()["status"] == "alive"
    assert sliced.status_code == 200


async def test_concurrent_slice_limit_returns_stable_busy_response(authorized_client, tmp_path: Path):
    from app.api.dependencies import SliceAdmission, SliceJobManager

    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    original_slice = orchestrator.slice
    entered = threading.Event()
    release = threading.Event()

    def blocked_slice(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original_slice(*args, **kwargs)

    orchestrator.slice = blocked_slice
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    jobs = SliceJobManager(SliceAdmission(1), executor=pool)
    _override_runtime(app, _Runtime(orchestrator, {}, admission=jobs.admission, jobs=jobs))

    first_request = asyncio.create_task(_post(client))
    await _wait_for_thread_event(entered)
    busy = await asyncio.wait_for(_post(client), timeout=1)
    release.set()
    first = await asyncio.wait_for(first_request, timeout=2)
    pool.shutdown(wait=True)

    assert busy.status_code == 503
    assert busy.json() == {
        "success": False,
        "error": {"code": "slicer_busy", "message": "The slicer service is at its concurrent request limit."},
    }
    assert first.status_code == 200
    assert len(orchestrator.calls) == 1


async def _wait_for_thread_event(event: threading.Event) -> None:
    for _ in range(100):
        if event.is_set():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("worker did not start")


async def test_legacy_slice_is_offloaded_and_shares_artifact_admission_limit(
    authorized_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from app.api.dependencies import SliceAdmission, SliceJobManager

    app, client = authorized_client
    entered = threading.Event()
    release = threading.Event()

    def blocked_legacy(**_kwargs):
        entered.set()
        assert release.wait(timeout=2)
        return {
            "success": True,
            "filament_grams": "1.5",
            "print_minutes": "10",
            "profile_used": "bambu_a1.ini",
            "stats": {},
            "gcode": "; gcode",
        }

    monkeypatch.setattr("app.api.routes.slice.slice_model", blocked_legacy)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    jobs = SliceJobManager(SliceAdmission(1), executor=pool)
    runtime = _Runtime(_FakeOrchestrator(_success(tmp_path)), {}, admission=jobs.admission)
    runtime.jobs = jobs
    _override_runtime(app, runtime)

    first_request = asyncio.create_task(
        client.post(
            "/api/v1/slice",
            headers={"Authorization": f"Bearer {_TOKEN}"},
            files={"model_file": ("dragon.stl", b"solid", "application/octet-stream")},
        )
    )
    await _wait_for_thread_event(entered)

    live = await asyncio.wait_for(client.get("/health/live"), timeout=1)
    artifact_busy = await asyncio.wait_for(_post(client), timeout=1)
    legacy_busy = await asyncio.wait_for(
        client.post(
            "/api/v1/slice",
            headers={"Authorization": f"Bearer {_TOKEN}"},
            files={"model_file": ("dragon.stl", b"solid", "application/octet-stream")},
        ),
        timeout=1,
    )
    release.set()
    first = await asyncio.wait_for(first_request, timeout=2)
    pool.shutdown(wait=True)

    assert live.status_code == 200
    assert artifact_busy.status_code == 503
    assert artifact_busy.json()["error"]["code"] == "slicer_busy"
    assert legacy_busy.status_code == 503
    assert legacy_busy.json()["success"] is False
    assert isinstance(legacy_busy.json()["error"], str)
    assert first.status_code == 200


async def test_cancelled_request_retains_slot_and_workspace_until_real_worker_finishes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from app.api.dependencies import SliceAdmission, SliceJobManager
    from app.api.routes.slice import slice_artifact_endpoint

    entered = threading.Event()
    release = threading.Event()
    workspace = tmp_path / "request-workspace"

    class Upload:
        filename = "dragon.stl"

        def __init__(self) -> None:
            self._chunks = iter([b"solid", b""])

        async def read(self, _size: int) -> bytes:
            return next(self._chunks)

        async def close(self) -> None:
            return None

    class BlockingOrchestrator:
        def slice(self, *_args):
            entered.set()
            assert release.wait(timeout=2)
            return OrchestratedResult(None, False, None, ())

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    jobs = SliceJobManager(SliceAdmission(1), executor=pool)
    runtime = _Runtime(BlockingOrchestrator(), {}, admission=jobs.admission)
    runtime.jobs = jobs
    monkeypatch.setattr("app.api.routes.slice.tempfile.mkdtemp", lambda **_kwargs: str(workspace))

    request_task = asyncio.create_task(
        slice_artifact_endpoint(
            model_file=Upload(),
            profile_name=None,
            center="128,128",
            preserve_orientation=None,
            slicer_options=None,
            runtime=runtime,
        )
    )
    await _wait_for_thread_event(entered)
    request_task.cancel()
    await asyncio.sleep(0.02)
    request_task.cancel()
    await asyncio.sleep(0.02)

    assert not request_task.done()
    assert workspace.exists()
    assert await jobs.try_acquire() is None

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(request_task, timeout=2)

    assert not workspace.exists()
    next_lease = await jobs.try_acquire()
    assert next_lease is not None
    await next_lease.release()
    pool.shutdown(wait=True)


async def test_slice_job_shutdown_drains_running_workers():
    from app.api.dependencies import SliceAdmission, SliceJobManager

    entered = threading.Event()
    release = threading.Event()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    jobs = SliceJobManager(SliceAdmission(1), executor=pool)
    lease = await jobs.try_acquire()
    assert lease is not None

    def blocked_worker():
        entered.set()
        assert release.wait(timeout=2)
        return "done"

    run_task = asyncio.create_task(lease.run(blocked_worker))
    await _wait_for_thread_event(entered)
    shutdown_task = asyncio.create_task(jobs.shutdown())
    await asyncio.sleep(0.02)
    assert not shutdown_task.done()

    release.set()
    assert await asyncio.wait_for(run_task, timeout=2) == "done"
    await asyncio.wait_for(shutdown_task, timeout=2)
    await lease.release()
    pool.shutdown(wait=True)


async def test_workspace_creation_failure_releases_admission_and_closes_upload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from app.api.dependencies import SliceAdmission
    from app.api.routes.slice import slice_artifact_endpoint

    class Upload:
        filename = "dragon.stl"
        closed = False

        async def close(self) -> None:
            self.closed = True

    admission = SliceAdmission(1)
    runtime = _Runtime(_FakeOrchestrator(_success(tmp_path)), {}, admission=admission)
    upload = Upload()
    monkeypatch.setattr(
        "app.api.routes.slice.tempfile.mkdtemp",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("workspace unavailable")),
    )

    response = await slice_artifact_endpoint(model_file=upload, runtime=runtime)

    assert response.status_code == 503
    assert (
        response.body
        == b'{"success":false,"error":{"code":"slicer_unavailable","message":"The slicer service could not produce an artifact."}}'
    )
    assert upload.closed is True
    assert await admission.try_acquire() is True
    await admission.release()


async def test_slice_artifact_reads_only_bounded_one_mib_chunks(
    authorized_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    from starlette.datastructures import UploadFile

    _override_runtime(app, _Runtime(orchestrator, {}))
    original_read = UploadFile.read
    sizes: list[int] = []

    async def tracked_read(self, size: int = -1):
        sizes.append(size)
        return await original_read(self, size)

    monkeypatch.setattr(UploadFile, "read", tracked_read)

    response = await _post(client)

    assert response.status_code == 200
    assert sizes
    assert set(sizes) == {1024 * 1024}


async def test_slice_artifact_enforces_exact_upload_limit_and_removes_partial_workspace(
    authorized_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    request_workspace = tmp_path / "request-owned"
    _override_runtime(app, _Runtime(orchestrator, {}))
    monkeypatch.setattr(settings, "max_model_bytes", 4)
    monkeypatch.setattr("app.api.routes.slice.tempfile.mkdtemp", lambda **_kwargs: str(request_workspace))

    response = await _post(client, content=b"12345")

    assert response.status_code == 413
    assert response.json() == {
        "success": False,
        "error": {"code": "model_too_large", "message": "The uploaded model exceeds the 4 bytes limit."},
    }
    assert orchestrator.calls == []
    assert not request_workspace.exists()


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (RequestValidationError("unsupported_material", "Unsupported material."), "unsupported_material"),
        (RequestValidationError("unsupported_nozzle", "Unsupported nozzle."), "unsupported_nozzle"),
    ],
)
async def test_terminal_request_validation_returns_422_without_fallback(
    authorized_client, tmp_path: Path, error: RequestValidationError, expected_code: str
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(error)
    _override_runtime(app, _Runtime(orchestrator, {}))

    response = await _post(client)

    assert response.status_code == 422
    assert response.json() == {
        "success": False,
        "error": {"code": expected_code, "message": error.message},
    }
    assert len(orchestrator.calls) == 1


async def test_malformed_options_return_422_without_calling_engine(authorized_client):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(AssertionError("engine must not run"))
    _override_runtime(app, _Runtime(orchestrator, {}))

    response = await client.post(
        "/api/v1/slice-artifact",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        files={"model_file": ("dragon.stl", b"solid", "application/octet-stream")},
        data={"slicer_options": "[not an object]"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "malformed_request"
    assert orchestrator.calls == []


async def test_no_available_engine_returns_generic_503_without_diagnostics(authorized_client, tmp_path: Path):
    app, client = authorized_client
    private_failure = OrchestratedFailure("bambu", "timeout", f"private {tmp_path}/model")
    orchestrator = _FakeOrchestrator(OrchestratedResult(None, True, private_failure, (private_failure,)))
    _override_runtime(app, _Runtime(orchestrator, {}))

    response = await _post(client)

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "error": {
            "code": "no_available_engine",
            "message": "No slicer engine could produce an artifact.",
        },
    }
    assert str(tmp_path) not in response.text


async def test_legacy_slice_keeps_json_shape_and_requires_auth(authorized_client, monkeypatch: pytest.MonkeyPatch):
    app, client = authorized_client
    _override_runtime(app, _Runtime(_FakeOrchestrator(AssertionError("artifact engine must not run")), {}))

    unauthorized = await client.post(
        "/api/v1/slice",
        files={"model_file": ("dragon.stl", b"solid", "application/octet-stream")},
    )
    assert unauthorized.status_code == 401

    monkeypatch.setattr(
        "app.api.routes.slice.slice_model",
        lambda **_kwargs: {
            "success": True,
            "filament_grams": "1.5",
            "print_minutes": "10",
            "profile_used": "bambu_a1.ini",
            "stats": {},
            "gcode": "; gcode",
        },
    )
    authorized = await client.post(
        "/api/v1/slice",
        headers={"Authorization": f"Bearer {_TOKEN}"},
        files={"model_file": ("dragon.stl", b"solid", "application/octet-stream")},
    )

    assert authorized.status_code == 200
    assert set(authorized.json()) == {
        "success",
        "error",
        "filament_grams",
        "print_minutes",
        "profile_used",
        "stats",
        "gcode",
    }


def test_default_upload_and_metadata_limits_are_exact():
    assert settings.max_model_bytes == 268435456
    assert settings.metadata_header_max_bytes == 6144
