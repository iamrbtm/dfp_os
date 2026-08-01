from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from flask import current_app, has_app_context

_METADATA_HEADER = "X-DFPOS-Slicer-Metadata"
_METADATA_HEADER_MAX_BYTES = 6144
_METADATA_FIELDS = frozenset(
    {
        "success",
        "engine_key",
        "engine_name",
        "engine_version",
        "fallback_used",
        "primary_failure",
        "filament_grams",
        "print_minutes",
        "layer_count",
        "profile_ids",
        "artifact_filename",
        "artifact_media_type",
        "artifact_size",
        "artifact_sha256",
        "direct_print_eligible",
        "estimate_only",
    }
)
_PRIMARY_FAILURE_FIELDS = frozenset({"engine_key", "code", "message"})
_SAFE_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ERROR_BODY_MAX_BYTES = 4096
_ERROR_TEXT_MAX_CHARACTERS = 600
_ARTIFACT_CHUNK_BYTES = 1024 * 1024


class SlicerClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        enabled: bool = True,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.enabled = enabled
        self.transport = transport

    def is_configured(self) -> bool:
        return bool(self.enabled and self.base_url and self.token)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "DFPos Slicer service is not configured."}
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=600.0,
            ) as client:
                response = client.request(method, path, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            current_app.logger.warning("slicer service error: %s", exc)
            try:
                return {"success": False, "error": exc.response.json()}
            except ValueError:
                return {"success": False, "error": str(exc)}
        except httpx.RequestError as exc:
            current_app.logger.warning("slicer service unavailable: %s", exc)
            return {"success": False, "error": str(exc)}

    def health_ready(self) -> dict[str, Any]:
        return self._request("GET", "/health/ready")

    def slice(
        self,
        model_file_path: str,
        profile_name: str | None = None,
        center: str | None = "128,128",
        slicer_options: dict | None = None,
        preserve_orientation: bool | None = None,
    ) -> dict[str, Any]:
        import json

        options_json = json.dumps(slicer_options) if slicer_options else None

        with open(model_file_path, "rb") as f:
            files = {"model_file": (model_file_path, f)}
            data = {}
            if profile_name:
                data["profile_name"] = profile_name
            if center is not None:
                data["center"] = center
            if slicer_options:
                data["slicer_options"] = options_json
            if preserve_orientation is not None:
                data["preserve_orientation"] = str(preserve_orientation).lower()
            return self._request("POST", "/api/v1/slice", files=files, data=data)

    def slice_artifact(
        self,
        model_file_path: str | Path,
        workspace: str | Path,
        profile_name: str | None = None,
        center: str | None = "128,128",
        slicer_options: dict | None = None,
        preserve_orientation: bool | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "DFPos Slicer service is not configured."}

        destination: Path | None = None
        destination_created = False
        try:
            workspace_root = Path(workspace).resolve(strict=True)
            if not workspace_root.is_dir():
                raise ValueError("The slicer workspace is not a directory.")

            data: dict[str, str] = {}
            if profile_name:
                data["profile_name"] = profile_name
            if center is not None:
                data["center"] = center
            if slicer_options:
                data["slicer_options"] = json.dumps(slicer_options)
            if preserve_orientation is not None:
                data["preserve_orientation"] = str(preserve_orientation).lower()

            model_path = Path(model_file_path)
            with model_path.open("rb") as model_file:
                files = {"model_file": (model_path.name, model_file)}
                with httpx.Client(
                    base_url=self.base_url,
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=600.0,
                    transport=self.transport,
                ) as client:
                    with client.stream(
                        "POST",
                        "/api/v1/slice-artifact",
                        files=files,
                        data=data,
                    ) as response:
                        if response.status_code >= 400:
                            return _service_error(response)

                        metadata = _decode_metadata(response.headers.get(_METADATA_HEADER, ""))
                        response_media_type = (
                            response.headers.get("Content-Type", "").split(";", 1)[0].strip()
                        )
                        if response_media_type.lower() != metadata["artifact_media_type"].lower():
                            raise ValueError(
                                "The slicer artifact media type did not match its metadata."
                            )
                        content_length_header = response.headers.get("Content-Length", "")
                        if not re.fullmatch(r"[0-9]+", content_length_header):
                            raise ValueError("The slicer artifact Content-Length is invalid.")
                        expected_size = metadata["artifact_size"]
                        content_length = int(content_length_header)
                        if content_length != expected_size:
                            raise ValueError("The slicer artifact size did not match its metadata.")
                        destination = workspace_root / str(metadata["artifact_filename"])
                        if destination.parent.resolve() != workspace_root:
                            raise ValueError("The slicer artifact filename is unsafe.")

                        digest = hashlib.sha256()
                        actual_size = 0
                        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                        if hasattr(os, "O_NOFOLLOW"):
                            flags |= os.O_NOFOLLOW
                        descriptor = os.open(destination, flags, 0o600)
                        destination_created = True
                        with os.fdopen(descriptor, "wb") as artifact_file:
                            for chunk in response.iter_bytes(chunk_size=_ARTIFACT_CHUNK_BYTES):
                                if actual_size + len(chunk) > expected_size:
                                    raise ValueError(
                                        "The slicer artifact exceeded its declared size."
                                    )
                                artifact_file.write(chunk)
                                digest.update(chunk)
                                actual_size += len(chunk)

                        if actual_size != expected_size or actual_size != content_length:
                            raise ValueError("The slicer artifact size did not match its metadata.")
                        if digest.hexdigest() != metadata["artifact_sha256"]:
                            raise ValueError(
                                "The slicer artifact checksum did not match its metadata."
                            )

                        return {**metadata, "artifact_path": destination}
        except (OSError, ValueError, KeyError, httpx.HTTPError) as exc:
            if destination is not None and destination_created:
                destination.unlink(missing_ok=True)
            _log_warning("slicer artifact request failed: %s", exc)
            return {"success": False, "error": _safe_client_error(exc)}


def _decode_metadata(encoded: str) -> dict[str, Any]:
    try:
        encoded_bytes = encoded.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("The slicer metadata header is invalid.") from exc
    if not encoded or len(encoded_bytes) >= _METADATA_HEADER_MAX_BYTES:
        raise ValueError("The slicer metadata header is missing or too large.")
    unpadded = encoded.rstrip("=")
    supplied_padding = encoded[len(unpadded) :]
    required_padding = "=" * (-len(unpadded) % 4)
    if (
        not unpadded
        or not re.fullmatch(r"[A-Za-z0-9_-]+", unpadded)
        or supplied_padding not in {"", required_padding}
        or len(unpadded) % 4 == 1
    ):
        raise ValueError("The slicer metadata header is invalid.")
    payload = base64.b64decode(
        (unpadded + required_padding).encode("ascii"),
        altchars=b"-_",
        validate=True,
    )
    if len(payload) > (_METADATA_HEADER_MAX_BYTES * 3) // 4:
        raise ValueError("The slicer metadata header is invalid.")
    metadata = json.loads(payload.decode("utf-8"))
    if not isinstance(metadata, dict) or set(metadata) != _METADATA_FIELDS:
        raise ValueError("The slicer metadata header is invalid.")
    _validate_metadata(metadata)
    return metadata


def _validate_metadata(metadata: dict[str, Any]) -> None:
    if metadata["success"] is not True:
        raise ValueError("The slicer metadata header is invalid.")

    for field_name in ("engine_key", "engine_name", "engine_version"):
        _require_text(metadata[field_name], maximum=128)
    for field_name in ("fallback_used", "direct_print_eligible", "estimate_only"):
        if type(metadata[field_name]) is not bool:
            raise ValueError("The slicer metadata header is invalid.")
    for field_name in ("filament_grams", "print_minutes"):
        value = metadata[field_name]
        if not isinstance(value, str):
            raise ValueError("The slicer metadata header is invalid.")
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("The slicer metadata header is invalid.") from exc
        if not number.is_finite() or number < 0:
            raise ValueError("The slicer metadata header is invalid.")

    layer_count = metadata["layer_count"]
    if layer_count is not None and (type(layer_count) is not int or layer_count < 0):
        raise ValueError("The slicer metadata header is invalid.")

    profile_ids = metadata["profile_ids"]
    if not isinstance(profile_ids, dict) or len(profile_ids) > 16:
        raise ValueError("The slicer metadata header is invalid.")
    for key, value in profile_ids.items():
        _require_text(key, maximum=64)
        _require_text(value, maximum=256)

    filename = metadata["artifact_filename"]
    if not isinstance(filename, str) or not _SAFE_FILENAME.fullmatch(filename):
        raise ValueError("The slicer metadata header is invalid.")
    _require_text(metadata["artifact_media_type"], maximum=255)

    artifact_size = metadata["artifact_size"]
    if type(artifact_size) is not int or artifact_size < 0:
        raise ValueError("The slicer metadata header is invalid.")
    artifact_sha256 = metadata["artifact_sha256"]
    if not isinstance(artifact_sha256, str) or not _SHA256.fullmatch(artifact_sha256):
        raise ValueError("The slicer metadata header is invalid.")

    primary_failure = metadata["primary_failure"]
    if primary_failure is not None:
        if not isinstance(primary_failure, dict) or set(primary_failure) != _PRIMARY_FAILURE_FIELDS:
            raise ValueError("The slicer metadata header is invalid.")
        _require_text(primary_failure["engine_key"], maximum=128)
        _require_text(primary_failure["code"], maximum=128)
        _require_text(primary_failure["message"], maximum=512)


def _require_text(value: Any, *, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("The slicer metadata header is invalid.")


def _service_error(response: httpx.Response) -> dict[str, Any]:
    generic = {
        "success": False,
        "error": f"Slicer service returned HTTP {response.status_code}.",
    }
    body = bytearray()
    for chunk in response.iter_bytes(chunk_size=_ERROR_BODY_MAX_BYTES + 1):
        remaining = _ERROR_BODY_MAX_BYTES - len(body)
        if len(chunk) > remaining:
            return generic
        body.extend(chunk)
    try:
        payload = json.loads(bytes(body).decode("utf-8"))
    except UnicodeDecodeError, json.JSONDecodeError:
        return generic
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return generic
    error = payload["error"]
    code = error.get("code")
    message = error.get("message")
    if not isinstance(code, str) or not isinstance(message, str):
        return generic
    safe_code = re.sub(r"[^A-Za-z0-9_.-]", "", code)[:128]
    safe_message = " ".join(
        "".join(
            character for character in message if ord(character) >= 32 and ord(character) != 127
        ).split()
    )[:_ERROR_TEXT_MAX_CHARACTERS]
    if not safe_code or not safe_message:
        return generic
    return {"success": False, "error": f"{safe_code}: {safe_message}"}


def _safe_client_error(exc: Exception) -> str:
    if isinstance(exc, OSError):
        return "The slicer artifact could not be written safely."
    if isinstance(exc, httpx.HTTPError):
        return "The slicer artifact response was interrupted or unavailable."
    if isinstance(exc, KeyError):
        return "The slicer artifact response is missing a required header or field."
    message = " ".join(
        "".join(
            character for character in str(exc) if ord(character) >= 32 and ord(character) != 127
        ).split()
    )[:_ERROR_TEXT_MAX_CHARACTERS]
    return message or "The slicer artifact response is invalid."


def _log_warning(message: str, *args: Any) -> None:
    if has_app_context():
        current_app.logger.warning(message, *args)


def get_slicer_client() -> SlicerClient:
    config = current_app.config
    return SlicerClient(
        base_url=config.get("SLICER_SERVICE_URL", ""),
        token=config.get("SLICER_INTERNAL_API_TOKEN", ""),
        enabled=config.get("SLICER_ENABLED", False),
    )
