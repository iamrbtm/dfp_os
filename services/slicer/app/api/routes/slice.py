from __future__ import annotations

import base64
import json
import logging
import shutil
import tempfile
from pathlib import Path, PurePath, PureWindowsPath

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from app.api.auth import AuthenticatedAPIRoute
from app.api.dependencies import SlicerRuntime, get_slicer_runtime
from app.config import settings
from app.schemas.slice import SliceResponse
from app.services.engines.base import RequestValidationError, SliceOptions, safe_artifact_filename
from app.services.engines.orchestrator import OrchestratedResult
from app.services.slicer import slice_model

router = APIRouter(tags=["slicing"], route_class=AuthenticatedAPIRoute)

_CHUNK_BYTES = 1024 * 1024
_METADATA_HEADER = "X-DFPOS-Slicer-Metadata"
_LOGGER = logging.getLogger(__name__)


class _ModelTooLarge(Exception):
    pass


class _MetadataTooLarge(Exception):
    pass


@router.post("/slice-artifact")
async def slice_artifact_endpoint(
    model_file: UploadFile = File(...),
    profile_name: str | None = Form(None),
    center: str | None = Form("128,128"),
    preserve_orientation: bool | None = Form(None),
    slicer_options: str | None = Form(None),
    runtime: SlicerRuntime = Depends(get_slicer_runtime),
):
    workspace = Path(tempfile.mkdtemp(prefix="dfpos-slicer-request-"))
    response_owns_workspace = False
    try:
        uploaded_name = _safe_upload_filename(model_file.filename)
        model_path = workspace / uploaded_name
        await _copy_upload(model_file, model_path)
        options_payload = _parse_options(slicer_options)
        options_payload["model_filename"] = uploaded_name
        if center is not None:
            options_payload["center"] = center
        options = SliceOptions.from_request(profile_name, options_payload, preserve_orientation)

        result = runtime.orchestrator.slice(model_path, workspace, options)
        if not result.success or result.artifact is None:
            return _error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "no_available_engine",
                "No slicer engine could produce an artifact.",
            )

        artifact_path = _safe_workspace_artifact(result, workspace)
        artifact_filename = safe_artifact_filename(result.artifact.artifact_filename)
        metadata = _public_metadata(result, artifact_filename)
        encoded_metadata = _encode_metadata(metadata)
        response = FileResponse(
            artifact_path,
            media_type=result.artifact.artifact_media_type,
            filename=artifact_filename,
            headers={_METADATA_HEADER: encoded_metadata},
            background=BackgroundTask(_cleanup_workspace, workspace),
        )
        response_owns_workspace = True
        return response
    except _ModelTooLarge:
        return _error_response(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "model_too_large",
            "The uploaded model exceeds the 256 MiB limit.",
        )
    except _MetadataTooLarge:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "metadata_too_large",
            "The slicer result metadata exceeds the configured response limit.",
        )
    except RequestValidationError as exc:
        return _error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code, exc.message)
    except json.JSONDecodeError, TypeError, ValueError:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "malformed_request",
            "The slicer options must be a JSON object.",
        )
    except Exception:
        _LOGGER.exception("Slice artifact request failed.")
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "slicer_unavailable",
            "The slicer service could not produce an artifact.",
        )
    finally:
        await model_file.close()
        if not response_owns_workspace:
            _cleanup_workspace(workspace)


@router.post("/slice", response_model=SliceResponse)
async def slice_endpoint(
    model_file: UploadFile = File(...),
    profile_name: str | None = Form(None),
    center: str | None = Form("128,128"),
    preserve_orientation: bool | None = Form(None),
    slicer_options: str | None = Form(None),
):
    workspace = Path(tempfile.mkdtemp(prefix="dfpos-slicer-legacy-"))
    try:
        uploaded_name = _safe_upload_filename(model_file.filename)
        model_path = workspace / uploaded_name
        await _copy_upload(model_file, model_path)
        options = _parse_options(slicer_options)
        return slice_model(
            model_path=str(model_path),
            profile_name=profile_name,
            center=center,
            slicer_options=options or None,
            preserve_orientation=preserve_orientation,
        )
    except _ModelTooLarge:
        return _error_response(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "model_too_large",
            "The uploaded model exceeds the 256 MiB limit.",
        )
    except json.JSONDecodeError, TypeError, ValueError:
        return SliceResponse(success=False, error="The slicer options must be a JSON object.")
    except Exception:
        _LOGGER.exception("Legacy slice request failed.")
        return SliceResponse(success=False, error="Slicing failed.")
    finally:
        await model_file.close()
        _cleanup_workspace(workspace)


async def _copy_upload(model_file: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    with destination.open("wb") as target:
        while chunk := await model_file.read(_CHUNK_BYTES):
            total_bytes += len(chunk)
            if total_bytes > settings.max_model_bytes:
                raise _ModelTooLarge
            target.write(chunk)


def _safe_upload_filename(value: str | None) -> str:
    uploaded_name = value or "model.stl"
    basename = PurePath(PureWindowsPath(uploaded_name).name).name or "model.stl"
    return safe_artifact_filename(basename)


def _parse_options(value: str | None) -> dict[str, object]:
    if value is None or not value.strip():
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise TypeError("slicer_options must be an object")
    return parsed


def _safe_workspace_artifact(result: OrchestratedResult, workspace: Path) -> Path:
    artifact = result.artifact
    if artifact is None:
        raise RuntimeError("missing artifact")
    workspace_root = workspace.resolve()
    artifact_path = artifact.artifact_path.resolve(strict=True)
    if not artifact_path.is_file() or not artifact_path.is_relative_to(workspace_root):
        raise RuntimeError("artifact is outside its request workspace")
    return artifact_path


def _public_metadata(result: OrchestratedResult, artifact_filename: str) -> dict[str, object]:
    artifact = result.artifact
    if artifact is None:
        raise RuntimeError("missing artifact")
    primary_failure = None
    if result.primary_failure is not None:
        primary_failure = {
            "engine_key": result.primary_failure.engine_key,
            "code": result.primary_failure.code,
            "message": result.primary_failure.message,
        }
    return {
        "success": True,
        "engine_key": artifact.engine_key,
        "engine_name": artifact.engine_name,
        "engine_version": artifact.engine_version,
        "fallback_used": result.fallback_used,
        "primary_failure": primary_failure,
        "filament_grams": str(artifact.filament_grams),
        "print_minutes": str(artifact.print_minutes),
        "layer_count": artifact.layer_count,
        "profile_ids": artifact.profile_ids,
        "artifact_filename": artifact_filename,
        "artifact_media_type": artifact.artifact_media_type,
        "artifact_size": artifact.artifact_size,
        "artifact_sha256": artifact.artifact_sha256,
        "direct_print_eligible": artifact.direct_print_eligible,
        "estimate_only": artifact.estimate_only,
    }


def _encode_metadata(metadata: dict[str, object]) -> str:
    payload = json.dumps(metadata, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    if len(encoded) >= settings.metadata_header_max_bytes:
        raise _MetadataTooLarge
    return encoded.decode("ascii")


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _cleanup_workspace(workspace: Path) -> None:
    shutil.rmtree(workspace, ignore_errors=True)
