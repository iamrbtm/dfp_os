from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import stat
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
_DEFAULT_ARTIFACT_MAX_BYTES = 512 * 1024 * 1024
_PUBLIC_BAMBU_FAILURE_MESSAGES = {
    "archive_limit_exceeded": "Bambu Studio output exceeded a safety limit.",
    "duplicate_profile": "Bambu Studio profile configuration is invalid.",
    "engine_exception": "Bambu Studio failed unexpectedly.",
    "engine_failure": "Bambu Studio failed.",
    "executable_missing": "Bambu Studio is unavailable.",
    "execution_failed": "Bambu Studio execution failed.",
    "invalid_output": "Bambu Studio produced an invalid output artifact.",
    "invalid_package": "Bambu Studio produced an invalid output package.",
    "invalid_profile": "Bambu Studio profile configuration is invalid.",
    "missing_gcode": "Bambu Studio output did not contain plate G-code.",
    "missing_output": "Bambu Studio did not produce an output artifact.",
    "missing_stats": "Bambu Studio output did not contain required estimates.",
    "probe_failed": "Bambu Studio failed its runtime availability check.",
    "probe_timeout": "Bambu Studio runtime availability check timed out.",
    "profile_cycle": "Bambu Studio profile configuration is invalid.",
    "profile_missing": "Bambu Studio required profile is unavailable.",
    "profile_root_missing": "Bambu Studio profile configuration is unavailable.",
    "profile_write_failed": "Bambu Studio could not prepare resolved profiles.",
    "timeout": "Bambu Studio timed out.",
    "version_mismatch": "Bambu Studio runtime version is unsupported.",
    "version_unrecognized": "Bambu Studio runtime version could not be verified.",
    "workspace_error": "Bambu Studio could not prepare its workspace.",
    "workspace_unavailable": "Bambu Studio could not prepare its profile workspace.",
}
_SECURE_DIR_FD_SUPPORTED = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and all(function in os.supports_dir_fd for function in (os.open, os.stat, os.unlink))
)


class SlicerClient:
    """Internal slicer HTTP client with an exclusive private-workspace contract.

    Artifact callers must supply a real, non-symlink directory owned by the
    current effective user with mode exactly ``0700``. The caller must retain
    exclusive control of that directory and must not rename, replace, chmod,
    or share it until the returned ``artifact_path`` has been consumed or
    persisted. Directory-FD pinning protects the transfer from path swaps; it
    does not claim immunity from a same-UID caller that violates this contract
    after the method returns.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        enabled: bool = True,
        max_artifact_bytes: int = _DEFAULT_ARTIFACT_MAX_BYTES,
        transport: httpx.BaseTransport | None = None,
    ):
        if type(max_artifact_bytes) is not int or max_artifact_bytes <= 0:
            raise ValueError("max_artifact_bytes must be a positive integer")
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.enabled = enabled
        self.max_artifact_bytes = max_artifact_bytes
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
        """Stream one native artifact into the caller-owned private workspace.

        ``workspace`` remains caller-owned. Keep its exact inode, ownership,
        and ``0700`` mode unchanged until the successful result's
        ``artifact_path`` is consumed or persisted.
        """

        if not self.is_configured():
            return {"success": False, "error": "DFPos Slicer service is not configured."}

        workspace_path = Path(workspace)
        workspace_fd: int | None = None
        workspace_identity: tuple[int, int] | None = None
        artifact_filename: str | None = None
        artifact_identity: tuple[int, int] | None = None
        try:
            workspace_fd, workspace_identity = _open_workspace_fd(workspace_path)

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
                        if expected_size > self.max_artifact_bytes:
                            raise ValueError(
                                "The slicer artifact exceeds the configured size limit."
                            )
                        artifact_filename = metadata["artifact_filename"]
                        destination = workspace_path / artifact_filename

                        digest = hashlib.sha256()
                        actual_size = 0
                        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                        descriptor = os.open(
                            artifact_filename,
                            flags,
                            0o600,
                            dir_fd=workspace_fd,
                        )
                        try:
                            created_stat = os.fstat(descriptor)
                            _validate_private_artifact_stat(created_stat)
                        except BaseException:
                            try:
                                os.close(descriptor)
                            finally:
                                _unlink_created_artifact(workspace_fd, artifact_filename)
                            raise
                        artifact_identity = (created_stat.st_dev, created_stat.st_ino)
                        try:
                            artifact_stream = os.fdopen(descriptor, "wb")
                        except BaseException:
                            os.close(descriptor)
                            raise
                        with artifact_stream as artifact_file:
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
                        final_stat = os.stat(
                            artifact_filename,
                            dir_fd=workspace_fd,
                            follow_symlinks=False,
                        )
                        if (
                            final_stat.st_dev,
                            final_stat.st_ino,
                        ) != artifact_identity or final_stat.st_size != actual_size:
                            raise ValueError("The slicer artifact file identity changed.")
                        _validate_private_artifact_stat(final_stat)
                        _verify_workspace_path_identity(workspace_path, workspace_identity)

                        return {**metadata, "artifact_path": destination}
        except (OSError, ValueError, KeyError, httpx.HTTPError) as exc:
            if workspace_fd is not None and artifact_filename and artifact_identity:
                _unlink_matching_artifact(workspace_fd, artifact_filename, artifact_identity)
            _log_warning("slicer artifact request failed: %s", exc)
            return {"success": False, "error": _safe_client_error(exc)}
        finally:
            if workspace_fd is not None:
                os.close(workspace_fd)


def _open_workspace_fd(workspace: Path) -> tuple[int, tuple[int, int]]:
    if not _SECURE_DIR_FD_SUPPORTED:
        raise ValueError("Secure slicer workspace operations are unavailable on this platform.")
    try:
        before = os.lstat(workspace)
    except OSError as exc:
        raise ValueError("The slicer workspace is not an accessible real directory.") from exc
    _validate_private_workspace_stat(before)

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        workspace_fd = os.open(workspace, flags)
    except OSError as exc:
        raise ValueError("The slicer workspace could not be opened safely.") from exc

    try:
        opened = os.fstat(workspace_fd)
    except BaseException:
        os.close(workspace_fd)
        raise
    identity = (opened.st_dev, opened.st_ino)
    try:
        _validate_private_workspace_stat(opened)
    except BaseException:
        os.close(workspace_fd)
        raise
    if identity != (before.st_dev, before.st_ino):
        os.close(workspace_fd)
        raise ValueError("The slicer workspace changed while it was being opened.")
    return workspace_fd, identity


def _verify_workspace_path_identity(workspace: Path, identity: tuple[int, int]) -> None:
    try:
        current = os.lstat(workspace)
    except OSError as exc:
        raise ValueError("The slicer workspace changed during artifact transfer.") from exc
    _validate_private_workspace_stat(current)
    if (current.st_dev, current.st_ino) != identity:
        raise ValueError("The slicer workspace changed during artifact transfer.")


def _validate_private_workspace_stat(value: os.stat_result) -> None:
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        raise ValueError("The slicer workspace must be a real directory, not a symlink.")
    if value.st_uid != os.geteuid():
        raise ValueError("The slicer workspace must be owned by the current effective user.")
    if stat.S_IMODE(value.st_mode) != 0o700:
        raise ValueError("The slicer workspace mode must be exactly 0700.")


def _validate_private_artifact_stat(value: os.stat_result) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o600
    ):
        raise ValueError("The slicer artifact must be a private regular file.")


def _unlink_created_artifact(workspace_fd: int, artifact_filename: str) -> None:
    try:
        os.unlink(artifact_filename, dir_fd=workspace_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        _log_warning("slicer artifact cleanup failed: %s", exc)


def _unlink_matching_artifact(
    workspace_fd: int,
    artifact_filename: str,
    artifact_identity: tuple[int, int],
) -> None:
    try:
        current = os.stat(
            artifact_filename,
            dir_fd=workspace_fd,
            follow_symlinks=False,
        )
        if (current.st_dev, current.st_ino) == artifact_identity:
            os.unlink(artifact_filename, dir_fd=workspace_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        _log_warning("slicer artifact cleanup failed: %s", exc)


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
    canonical = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    if not secrets.compare_digest(canonical, unpadded):
        raise ValueError("The slicer metadata header is invalid.")
    metadata = json.loads(payload.decode("utf-8"))
    if not isinstance(metadata, dict) or set(metadata) != _METADATA_FIELDS:
        raise ValueError("The slicer metadata header is invalid.")
    _validate_metadata(metadata)
    _validate_engine_semantics(metadata)
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


def _validate_engine_semantics(metadata: dict[str, Any]) -> None:
    engine_key = metadata["engine_key"]
    primary_failure = metadata["primary_failure"]
    if engine_key == "bambu":
        valid = (
            metadata["engine_name"] == "Bambu Studio"
            and metadata["engine_version"] == "2.7.1.62"
            and metadata["artifact_filename"].endswith(".gcode.3mf")
            and metadata["artifact_media_type"] == "application/vnd.bambulab.gcode-3mf"
            and metadata["direct_print_eligible"] is True
            and metadata["estimate_only"] is False
            and metadata["fallback_used"] is False
            and primary_failure is None
        )
    elif engine_key == "prusa":
        valid = (
            metadata["engine_name"] == "PrusaSlicer"
            and re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", metadata["engine_version"]) is not None
            and metadata["artifact_filename"].endswith(".gcode")
            and not metadata["artifact_filename"].endswith(".gcode.3mf")
            and metadata["artifact_media_type"] == "text/x.gcode"
            and metadata["direct_print_eligible"] is False
            and metadata["estimate_only"] is True
            and metadata["fallback_used"] is True
            and isinstance(primary_failure, dict)
            and primary_failure["engine_key"] == "bambu"
            and primary_failure["code"] in _PUBLIC_BAMBU_FAILURE_MESSAGES
            and primary_failure["message"]
            == _PUBLIC_BAMBU_FAILURE_MESSAGES.get(primary_failure["code"])
        )
    else:
        valid = False
    if not valid:
        raise ValueError("The slicer metadata engine/artifact contract is invalid.")


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
        max_artifact_bytes=config.get("SLICER_ARTIFACT_MAX_BYTES", _DEFAULT_ARTIFACT_MAX_BYTES),
    )
