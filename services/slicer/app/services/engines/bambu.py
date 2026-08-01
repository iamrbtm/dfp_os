from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.services.engines.bambu_profiles import BambuProfileError, BambuProfileResolver, ResolvedBambuProfiles
from app.services.engines.base import (
    SUPPORTED_MATERIALS,
    SUPPORTED_MODEL_SUFFIXES,
    SUPPORTED_PRINTERS,
    EngineArtifact,
    EngineFailure,
    EngineProbe,
    RequestValidationError,
    SliceOptions,
    safe_artifact_filename,
    sha256_file,
)
from app.services.engines.stats import InvalidGcodeStatsError, _normalize_fill_density, _parse_gcode_stats


_PLATE_GCODE = re.compile(r"Metadata/plate_\d+\.gcode")
_ABSOLUTE_PATH = re.compile(r"(?<![\w.])(?:[A-Za-z]:[\\/]|/)(?:[^\s:;,]+[\\/])*[^\s:;,]*")


class BambuEngine:
    engine_key = "bambu"
    engine_name = "Bambu Studio"

    def __init__(
        self,
        executable: str,
        profile_resolver: BambuProfileResolver,
        timeout: int = 600,
    ) -> None:
        self.executable = executable
        self.profile_resolver = profile_resolver
        self.timeout = timeout
        self._engine_version = "unknown"

    def probe(self) -> EngineProbe:
        try:
            proc = subprocess.run(
                [self.executable, "--help"],
                capture_output=True,
                timeout=10,
                shell=False,
            )
        except FileNotFoundError:
            return self._probe_failure("executable_missing")
        except subprocess.TimeoutExpired:
            return self._probe_failure("probe_timeout")
        except Exception:
            return self._probe_failure("probe_failed")

        if proc.returncode != 0:
            return self._probe_failure("probe_failed", stderr=self._stderr(proc))

        self._engine_version = self._version(proc)
        return EngineProbe(
            engine_key=self.engine_key,
            engine_name=self.engine_name,
            available=True,
            engine_version=self._engine_version,
        )

    def slice(self, model_path: Path, workspace: Path, options: SliceOptions) -> EngineArtifact | EngineFailure:
        model_path = Path(model_path)
        workspace = Path(workspace)
        self._validate_request(model_path, options)

        try:
            profiles = self.profile_resolver.resolve(options.printer, options.material, workspace)
        except BambuProfileError as exc:
            if exc.code in {"unsupported_printer", "unsupported_material"}:
                raise RequestValidationError(exc.code, exc.message) from exc
            return self._failure(exc.code, "Bambu Studio profiles are unavailable.")

        try:
            workspace.mkdir(parents=True, exist_ok=True)
        except OSError:
            return self._failure("workspace_error", "Could not prepare the Bambu Studio workspace.")

        artifact_filename = self._artifact_filename(model_path)
        artifact_path = workspace / artifact_filename
        try:
            artifact_path.unlink(missing_ok=True)
        except OSError:
            return self._failure("workspace_error", "Could not prepare the Bambu Studio output path.")

        command = self._command(model_path, artifact_path, profiles, options)
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                timeout=self.timeout,
                shell=False,
            )
        except FileNotFoundError:
            return self._failure("executable_missing", "Bambu Studio is unavailable.")
        except subprocess.TimeoutExpired:
            return self._failure("timeout", f"Bambu Studio timed out after {self.timeout}s.")
        except Exception:
            return self._failure("execution_failed", "Bambu Studio execution failed.")

        if proc.returncode != 0:
            return self._failure(
                "execution_failed",
                f"Bambu Studio exited with code {proc.returncode}.",
                stderr=self._stderr(proc),
            )
        if not artifact_path.is_file():
            return self._failure("missing_output", "Bambu Studio did not produce an output artifact.")

        stats = self._artifact_stats(artifact_path, workspace)
        if isinstance(stats, EngineFailure):
            return stats

        try:
            artifact_size = artifact_path.stat().st_size
            artifact_sha256 = sha256_file(artifact_path)
        except OSError:
            return self._failure("invalid_output", "Bambu Studio produced an unreadable output artifact.")

        return EngineArtifact(
            engine_key=self.engine_key,
            engine_name=self.engine_name,
            engine_version=self._engine_version,
            artifact_path=artifact_path,
            artifact_filename=artifact_filename,
            artifact_media_type="application/vnd.bambulab.gcode-3mf",
            artifact_size=artifact_size,
            artifact_sha256=artifact_sha256,
            filament_grams=stats["filament_grams"],
            print_minutes=stats["print_minutes"],
            layer_count=stats["layer_count"],
            profile_ids=profiles.profile_ids,
            direct_print_eligible=True,
            estimate_only=False,
            diagnostics={"stats": stats},
        )

    def _command(
        self,
        model_path: Path,
        artifact_path: Path,
        profiles: ResolvedBambuProfiles,
        options: SliceOptions,
    ) -> list[str]:
        values = options.slicer_options
        command = [
            self.executable,
            "--load-settings",
            f"{profiles.machine_path};{profiles.process_path}",
            "--load-filaments",
            str(profiles.filament_path),
            "--arrange",
            "1",
        ]
        if not options.preserve_orientation:
            command.append("--orient")

        for source_key, bambu_key in {
            "layer_height": "layer-height",
            "perimeters": "wall-loops",
            "top_solid_layers": "top-shell-layers",
            "bottom_solid_layers": "bottom-shell-layers",
            "infill_pattern": "sparse-infill-pattern",
            "brim_width": "brim-width",
        }.items():
            value = values.get(source_key)
            if value is not None and value != "":
                command.append(f"--{bambu_key}={value}")

        fill_density = _normalize_fill_density(values.get("infill_percent"))
        if fill_density is not None:
            command.append(f"--sparse-infill-density={fill_density}")

        supports = str(values.get("supports") or "none").strip().lower()
        if supports == "everywhere":
            command.extend(["--enable-support=1", "--support-on-build-plate-only=0"])
        elif supports == "build_plate":
            command.extend(["--enable-support=1", "--support-on-build-plate-only=1"])
        else:
            command.append("--enable-support=0")

        command.extend(["--slice", "0", "--export-3mf", str(artifact_path), str(model_path)])
        return command

    def _artifact_stats(self, artifact_path: Path, workspace: Path) -> dict[str, object] | EngineFailure:
        try:
            with zipfile.ZipFile(artifact_path) as archive:
                members = sorted(
                    info for info in archive.infolist() if not info.is_dir() and _PLATE_GCODE.fullmatch(info.filename)
                )
                if not members:
                    return self._failure("missing_gcode", "Bambu Studio output contains no plate G-code.")

                for member in members:
                    stats = self._member_stats(archive, member, workspace)
                    if stats is not None:
                        return stats
        except zipfile.BadZipFile, OSError, RuntimeError, ValueError:
            return self._failure("invalid_output", "Bambu Studio produced an invalid output artifact.")
        except InvalidGcodeStatsError:
            return self._failure("invalid_output", "Bambu Studio output contains malformed statistics.")

        return self._failure("missing_stats", "Bambu Studio output contains no required estimates.")

    @staticmethod
    def _member_stats(
        archive: zipfile.ZipFile,
        member: zipfile.ZipInfo,
        workspace: Path,
    ) -> dict[str, object] | None:
        temporary_path: Path | None = None
        try:
            with (
                archive.open(member) as source,
                tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=workspace,
                    prefix=".bambu-plate-",
                    suffix=".gcode",
                    delete=False,
                ) as target,
            ):
                temporary_path = Path(target.name)
                shutil.copyfileobj(source, target, length=1024 * 1024)
            return _parse_gcode_stats(temporary_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _validate_request(model_path: Path, options: SliceOptions) -> None:
        if options.printer not in SUPPORTED_PRINTERS:
            raise RequestValidationError("unsupported_printer", "The requested printer profile is unsupported.")

        try:
            nozzle = Decimal(str(options.nozzle_diameter))
        except InvalidOperation, ValueError:
            raise RequestValidationError("invalid_nozzle", "The nozzle diameter must be a decimal value.") from None
        if nozzle != Decimal("0.4"):
            raise RequestValidationError("unsupported_nozzle", "Only a 0.4 mm nozzle is supported.")

        if options.material not in SUPPORTED_MATERIALS:
            raise RequestValidationError("unsupported_material", "The requested material is unsupported.")

        actual_suffix = model_path.suffix.lower()
        if options.model_suffix not in SUPPORTED_MODEL_SUFFIXES or actual_suffix not in SUPPORTED_MODEL_SUFFIXES:
            raise RequestValidationError("unsupported_model_suffix", "The uploaded model file type is unsupported.")
        if actual_suffix != options.model_suffix:
            raise RequestValidationError(
                "model_suffix_mismatch", "The uploaded model file type does not match its request."
            )

        values = options.slicer_options
        if BambuEngine._as_bool(values.get("multicolor")) and not (
            actual_suffix == ".3mf" and BambuEngine._as_bool(values.get("use_embedded_settings"))
        ):
            raise RequestValidationError(
                "unsupported_multicolor",
                "Multicolor slicing requires a 3MF with embedded settings in this phase.",
            )

    @staticmethod
    def _as_bool(value: object) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _artifact_filename(model_path: Path) -> str:
        safe_source = safe_artifact_filename(model_path.name)
        return safe_artifact_filename(f"{Path(safe_source).stem}.gcode.3mf")

    def _probe_failure(self, code: str, *, stderr: str | None = None) -> EngineProbe:
        diagnostics: dict[str, object] = {"code": code}
        if stderr:
            diagnostics["stderr"] = stderr
        return EngineProbe(
            engine_key=self.engine_key,
            engine_name=self.engine_name,
            available=False,
            diagnostics=diagnostics,
        )

    def _failure(self, code: str, message: str, *, stderr: str | None = None) -> EngineFailure:
        diagnostics = {"stderr": stderr} if stderr else {}
        return EngineFailure(
            engine_key=self.engine_key,
            code=code,
            message=message,
            fallback_eligible=True,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _stderr(proc: subprocess.CompletedProcess[bytes]) -> str:
        stderr = proc.stderr
        value = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else str(stderr or "")
        return _ABSOLUTE_PATH.sub("[path]", value).strip()[:512]

    @staticmethod
    def _version(proc: subprocess.CompletedProcess[bytes]) -> str:
        values: list[str] = []
        for raw_value in (getattr(proc, "stdout", None), getattr(proc, "stderr", None)):
            values.append(
                raw_value.decode("utf-8", errors="replace") if isinstance(raw_value, bytes) else str(raw_value or "")
            )
        match = re.search(r"BambuStudio[-\s]+(\d+(?:\.\d+){3})", "\n".join(values), re.IGNORECASE)
        if match is None:
            return "unknown"
        return ".".join(str(int(part)) for part in match.group(1).split("."))
