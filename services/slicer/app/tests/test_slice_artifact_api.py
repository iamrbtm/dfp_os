from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from starlette.background import BackgroundTask
from starlette.responses import Response

from app.config import settings
from app.main import create_app
from app.services.engines.base import EngineArtifact, RequestValidationError
from app.services.engines.orchestrator import OrchestratedFailure, OrchestratedResult


@dataclass
class _Runtime:
    orchestrator: object
    engines: dict[str, object]


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
    monkeypatch.setattr(settings, "internal_api_token", "test-slicer-token")
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield app, client


@pytest.fixture(autouse=True)
def immediate_file_response(monkeypatch: pytest.MonkeyPatch):
    """Avoid Starlette's AnyIO file thread in the restricted test sandbox."""
    calls: list[tuple[Path, BackgroundTask]] = []

    def build_response(
        path: Path,
        *,
        media_type: str,
        filename: str,
        headers: dict[str, str],
        background: BackgroundTask,
    ) -> Response:
        assert isinstance(background, BackgroundTask)
        artifact_path = Path(path)
        content = artifact_path.read_bytes()
        calls.append((artifact_path, background))
        response_headers = {**headers, "Content-Disposition": f'attachment; filename="{filename}"'}
        background.func(*background.args, **background.kwargs)
        return Response(content=content, media_type=media_type, headers=response_headers)

    monkeypatch.setattr("app.api.routes.slice.FileResponse", build_response)
    return calls


async def _post(client: httpx.AsyncClient, *, token: str | None = "test-slicer-token", content: bytes = b"solid cube"):
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
    assert comparisons == [("test-slicer-token", "test-slicer-token")]


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


async def test_file_response_construction_failure_removes_request_workspace(
    authorized_client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    app, client = authorized_client
    orchestrator = _FakeOrchestrator(_success(tmp_path))
    request_workspace = tmp_path / "request-owned"
    _override_runtime(app, _Runtime(orchestrator, {}))
    monkeypatch.setattr("app.api.routes.slice.tempfile.mkdtemp", lambda **_kwargs: str(request_workspace))

    def fail_response(*_args, **_kwargs):
        raise RuntimeError("response construction failed")

    monkeypatch.setattr("app.api.routes.slice.FileResponse", fail_response)

    response = await _post(client)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "slicer_unavailable"
    assert not request_workspace.exists()


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
        "error": {"code": "model_too_large", "message": "The uploaded model exceeds the 256 MiB limit."},
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
        headers={"Authorization": "Bearer test-slicer-token"},
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
        headers={"Authorization": "Bearer test-slicer-token"},
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
