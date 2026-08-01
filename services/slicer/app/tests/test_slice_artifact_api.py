from __future__ import annotations

import base64
import asyncio
import json
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


class _UnlimitedAdmission:
    async def try_acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


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


@pytest.fixture(autouse=True)
def local_file_response_io(monkeypatch: pytest.MonkeyPatch):
    """Patch only AnyIO's broken worker-thread file boundary in this Python 3.14 sandbox."""

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

    async def run_sync(function, *args, **_kwargs):
        return function(*args)

    monkeypatch.setattr("starlette.responses.anyio.open_file", open_file)
    monkeypatch.setattr("starlette.responses.anyio.to_thread.run_sync", run_sync)


@pytest.fixture(autouse=True)
def immediate_slice_thread_offload(monkeypatch: pytest.MonkeyPatch):
    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr("app.api.routes.slice.asyncio.to_thread", run_inline)


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
    response = CleanupFileResponse(artifact, workspace=workspace, stat_result=artifact.stat())

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
    response = CleanupFileResponse(artifact, workspace=workspace)

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


async def test_live_endpoint_remains_responsive_while_slice_is_offloaded(
    authorized_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    _override_runtime(app, _Runtime(orchestrator, {}))
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_offload(function, *args, **kwargs):
        entered.set()
        await release.wait()
        return function(*args, **kwargs)

    monkeypatch.setattr("app.api.routes.slice.asyncio.to_thread", blocked_offload)

    slice_request = asyncio.create_task(_post(client))
    await asyncio.wait_for(entered.wait(), timeout=1)
    live = await asyncio.wait_for(client.get("/health/live"), timeout=1)
    release.set()
    sliced = await asyncio.wait_for(slice_request, timeout=1)

    assert live.status_code == 200
    assert live.json()["status"] == "alive"
    assert sliced.status_code == 200


async def test_concurrent_slice_limit_returns_stable_busy_response(
    authorized_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from app.api.dependencies import SliceAdmission

    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    _override_runtime(app, _Runtime(orchestrator, {}, admission=SliceAdmission(1)))
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_offload(function, *args, **kwargs):
        entered.set()
        await release.wait()
        return function(*args, **kwargs)

    monkeypatch.setattr("app.api.routes.slice.asyncio.to_thread", blocked_offload)

    first_request = asyncio.create_task(_post(client))
    await asyncio.wait_for(entered.wait(), timeout=1)
    busy = await asyncio.wait_for(_post(client), timeout=1)
    release.set()
    first = await asyncio.wait_for(first_request, timeout=1)

    assert busy.status_code == 503
    assert busy.json() == {
        "success": False,
        "error": {"code": "slicer_busy", "message": "The slicer service is at its concurrent request limit."},
    }
    assert first.status_code == 200
    assert len(orchestrator.calls) == 1


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
    _app, client = authorized_client

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
