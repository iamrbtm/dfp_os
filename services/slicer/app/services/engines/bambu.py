from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

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
from app.services.engines.stats import InvalidGcodeStatsError, _parse_gcode_stats


_PLATE_GCODE = re.compile(r"Metadata/plate_\d+\.gcode")
_ABSOLUTE_PATH = re.compile(r"(?<![\w.])(?:[A-Za-z]:[\\/]|/)(?:[^\s:;,]+[\\/])*[^\s:;,]*")
PINNED_ENGINE_VERSION = "2.7.1.62"
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 512
MAX_MEMBER_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
_REQUIRED_PACKAGE_PARTS = frozenset({"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"})
_ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_INFILL_PATTERNS = frozenset({"cubic", "grid", "gyroid", "honeycomb"})
_SUPPORT_MODES = frozenset({"none", "build_plate", "everywhere"})


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
        self._engine_version: str | None = None

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

        engine_version = self._version(proc)
        if engine_version == "unknown":
            return self._probe_failure("version_unrecognized")
        if engine_version != PINNED_ENGINE_VERSION:
            return self._probe_failure("version_mismatch", engine_version=engine_version)
        self._engine_version = engine_version
        return EngineProbe(
            engine_key=self.engine_key,
            engine_name=self.engine_name,
            available=True,
            engine_version=engine_version,
        )

    def slice(self, model_path: Path, workspace: Path, options: SliceOptions) -> EngineArtifact | EngineFailure:
        model_path = Path(model_path)
        workspace = Path(workspace)
        cli_options = self._validate_request(model_path, options)

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

        version_failure = self._ensure_version()
        if version_failure is not None:
            return version_failure

        command = self._command(model_path, artifact_path, profiles, options, cli_options)
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                timeout=self.timeout,
                shell=False,
            )
        except FileNotFoundError:
            self._discard_artifact(artifact_path)
            return self._failure("executable_missing", "Bambu Studio is unavailable.")
        except subprocess.TimeoutExpired:
            self._discard_artifact(artifact_path)
            return self._failure("timeout", f"Bambu Studio timed out after {self.timeout}s.")
        except Exception:
            self._discard_artifact(artifact_path)
            return self._failure("execution_failed", "Bambu Studio execution failed.")

        if proc.returncode != 0:
            self._discard_artifact(artifact_path)
            return self._failure(
                "execution_failed",
                f"Bambu Studio exited with code {proc.returncode}.",
                stderr=self._stderr(proc, workspace),
            )
        if not artifact_path.is_file():
            return self._failure("missing_output", "Bambu Studio did not produce an output artifact.")

        stats = self._artifact_stats(artifact_path, workspace)
        if isinstance(stats, EngineFailure):
            self._discard_artifact(artifact_path)
            return stats

        try:
            artifact_size = artifact_path.stat().st_size
            artifact_sha256 = sha256_file(artifact_path)
        except OSError:
            self._discard_artifact(artifact_path)
            return self._failure("invalid_output", "Bambu Studio produced an unreadable output artifact.")

        return EngineArtifact(
            engine_key=self.engine_key,
            engine_name=self.engine_name,
            engine_version=self._engine_version or PINNED_ENGINE_VERSION,
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
        cli_options: dict[str, str],
    ) -> list[str]:
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
            value = cli_options.get(source_key)
            if value is not None:
                command.append(f"--{bambu_key}={value}")

        fill_density = cli_options.get("infill_percent")
        if fill_density is not None:
            command.append(f"--sparse-infill-density={fill_density}")

        supports = cli_options["supports"]
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
            if artifact_path.stat().st_size > MAX_ARCHIVE_BYTES:
                return self._failure("archive_limit_exceeded", "Bambu Studio output exceeds the archive size limit.")
        except OSError:
            return self._failure("invalid_output", "Bambu Studio produced an unreadable output artifact.")

        try:
            with zipfile.ZipFile(artifact_path) as archive:
                package_failure = self._validate_package(archive)
                if package_failure is not None:
                    return package_failure

                members = sorted(
                    (
                        info
                        for info in archive.infolist()
                        if not info.is_dir() and _PLATE_GCODE.fullmatch(info.filename)
                    ),
                    key=self._plate_sort_key,
                )
                if not members:
                    return self._failure("missing_gcode", "Bambu Studio output contains no plate G-code.")

                plate_stats: list[dict[str, object]] = []
                for member in members:
                    stats = self._member_stats(archive, member, workspace)
                    if stats is None:
                        return self._failure(
                            "missing_stats",
                            "Bambu Studio output contains a plate without required estimates.",
                        )
                    plate_stats.append(stats)
                return self._aggregate_plate_stats(members, plate_stats)
        except zipfile.BadZipFile, OSError, RuntimeError, ValueError:
            return self._failure("invalid_output", "Bambu Studio produced an invalid output artifact.")
        except InvalidGcodeStatsError:
            return self._failure("invalid_output", "Bambu Studio output contains malformed statistics.")

    def _validate_package(self, archive: zipfile.ZipFile) -> EngineFailure | None:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            return self._failure("archive_limit_exceeded", "Bambu Studio output contains too many archive members.")

        names = [member.filename for member in members]
        if len(names) != len(set(names)):
            return self._failure("invalid_package", "Bambu Studio output contains duplicate package members.")
        if any(not self._safe_member_name(name) for name in names):
            return self._failure("invalid_package", "Bambu Studio output contains an unsafe package member.")

        total_uncompressed = 0
        for member in members:
            if member.flag_bits & 0x1 or member.compress_type not in _ALLOWED_COMPRESSION:
                return self._failure("invalid_package", "Bambu Studio output uses an unsupported package encoding.")
            if member.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                return self._failure("archive_limit_exceeded", "A Bambu Studio package member exceeds the size limit.")
            total_uncompressed += member.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                return self._failure("archive_limit_exceeded", "Bambu Studio output exceeds the expanded size limit.")
            if member.file_size and member.file_size / max(member.compress_size, 1) > MAX_COMPRESSION_RATIO:
                return self._failure(
                    "archive_limit_exceeded", "Bambu Studio output exceeds the compression ratio limit."
                )

        if not _REQUIRED_PACKAGE_PARTS.issubset(names):
            return self._failure("invalid_package", "Bambu Studio output is missing required 3MF package parts.")

        if archive.testzip() is not None:
            return self._failure("invalid_output", "Bambu Studio output failed its archive integrity check.")

        try:
            for required_part in _REQUIRED_PACKAGE_PARTS:
                ElementTree.fromstring(archive.read(required_part))
        except ElementTree.ParseError, KeyError, UnicodeError, ValueError:
            return self._failure("invalid_package", "Bambu Studio output contains an invalid 3MF package part.")
        return None

    @staticmethod
    def _safe_member_name(name: str) -> bool:
        if not name or "\\" in name or "\x00" in name:
            return False
        path = PurePosixPath(name)
        return not path.is_absolute() and ".." not in path.parts

    @staticmethod
    def _plate_sort_key(member: zipfile.ZipInfo) -> tuple[int, str]:
        match = re.fullmatch(r"Metadata/plate_(\d+)\.gcode", member.filename)
        return (int(match.group(1)) if match else 0, member.filename)

    @staticmethod
    def _aggregate_plate_stats(
        members: list[zipfile.ZipInfo],
        plate_stats: list[dict[str, object]],
    ) -> dict[str, object]:
        filament_grams = sum((stats["filament_grams"] for stats in plate_stats), start=Decimal("0"))
        print_minutes = sum((stats["print_minutes"] for stats in plate_stats), start=Decimal("0"))
        layer_values = [stats["layer_count"] for stats in plate_stats]
        layer_count = sum(layer_values) if all(value is not None for value in layer_values) else None
        return {
            "filament_grams": filament_grams,
            "print_minutes": print_minutes,
            "layer_count": layer_count,
            "filament_source_pattern": "aggregate"
            if len(plate_stats) > 1
            else plate_stats[0]["filament_source_pattern"],
            "time_source_pattern": "aggregate" if len(plate_stats) > 1 else plate_stats[0]["time_source_pattern"],
            "plate_members": [member.filename for member in members],
            "plate_stats": plate_stats,
        }

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
    def _validate_request(model_path: Path, options: SliceOptions) -> dict[str, str]:
        if options.printer not in SUPPORTED_PRINTERS:
            raise RequestValidationError("unsupported_printer", "The requested printer profile is unsupported.")

        try:
            nozzle = Decimal(str(options.nozzle_diameter))
        except InvalidOperation, ValueError:
            raise RequestValidationError("invalid_nozzle", "The nozzle diameter must be a decimal value.") from None
        if not nozzle.is_finite():
            raise RequestValidationError("invalid_nozzle", "The nozzle diameter must be a finite decimal value.")
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
        multicolor = BambuEngine._boolean_option(values, "multicolor", default=False)
        use_embedded_settings = BambuEngine._boolean_option(values, "use_embedded_settings", default=False)
        if multicolor and not (actual_suffix == ".3mf" and use_embedded_settings):
            raise RequestValidationError(
                "unsupported_multicolor",
                "Multicolor slicing requires a 3MF with embedded settings in this phase.",
            )

        normalized: dict[str, str] = {}
        for name, minimum, maximum, integer_only in (
            ("layer_height", Decimal("0.04"), Decimal("1"), False),
            ("perimeters", Decimal("1"), Decimal("20"), True),
            ("top_solid_layers", Decimal("0"), Decimal("30"), True),
            ("bottom_solid_layers", Decimal("0"), Decimal("30"), True),
            ("brim_width", Decimal("0"), Decimal("50"), False),
        ):
            if name in values:
                normalized[name] = BambuEngine._numeric_option(
                    name,
                    values[name],
                    minimum=minimum,
                    maximum=maximum,
                    integer_only=integer_only,
                )

        if "infill_percent" in values:
            normalized["infill_percent"] = BambuEngine._percent_option(values["infill_percent"])

        pattern_value = values.get("infill_pattern")
        if pattern_value is not None:
            if not isinstance(pattern_value, str) or pattern_value.strip().lower() not in _INFILL_PATTERNS:
                BambuEngine._raise_invalid_option("infill_pattern")
            normalized["infill_pattern"] = pattern_value.strip().lower()

        support_value = values.get("supports", "none")
        if not isinstance(support_value, str) or support_value.strip().lower() not in _SUPPORT_MODES:
            BambuEngine._raise_invalid_option("supports")
        normalized["supports"] = support_value.strip().lower()
        return normalized

    @staticmethod
    def _boolean_option(values: dict[str, object], name: str, *, default: bool) -> bool:
        if name not in values:
            return default
        value = values[name]
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        BambuEngine._raise_invalid_option(name)

    @staticmethod
    def _numeric_option(
        name: str,
        value: object,
        *,
        minimum: Decimal,
        maximum: Decimal,
        integer_only: bool,
    ) -> str:
        if isinstance(value, bool):
            BambuEngine._raise_invalid_option(name)
        try:
            number = Decimal(str(value))
        except InvalidOperation, ValueError:
            BambuEngine._raise_invalid_option(name)
        if not number.is_finite() or number < minimum or number > maximum:
            BambuEngine._raise_invalid_option(name)
        if integer_only and number != number.to_integral_value():
            BambuEngine._raise_invalid_option(name)
        return BambuEngine._decimal_text(number)

    @staticmethod
    def _percent_option(value: object) -> str:
        if isinstance(value, bool):
            BambuEngine._raise_invalid_option("infill_percent")
        raw = str(value).strip()
        has_percent = raw.endswith("%")
        number_text = raw[:-1].strip() if has_percent else raw
        try:
            percent = Decimal(number_text)
        except InvalidOperation, ValueError:
            BambuEngine._raise_invalid_option("infill_percent")
        if not percent.is_finite():
            BambuEngine._raise_invalid_option("infill_percent")
        if not has_percent and Decimal("0") <= percent <= Decimal("1"):
            percent *= Decimal("100")
        if percent < 0 or percent > 100:
            BambuEngine._raise_invalid_option("infill_percent")
        return f"{BambuEngine._decimal_text(percent)}%"

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    @staticmethod
    def _raise_invalid_option(name: str) -> None:
        raise RequestValidationError(
            "invalid_slicer_option",
            f"The slicer option {name} is invalid.",
        )

    @staticmethod
    def _artifact_filename(model_path: Path) -> str:
        safe_source = safe_artifact_filename(model_path.name)
        return safe_artifact_filename(f"{Path(safe_source).stem}.gcode.3mf")

    def _ensure_version(self) -> EngineFailure | None:
        if self._engine_version is not None:
            return None
        probe = self.probe()
        if probe.available:
            return None
        code = str(probe.diagnostics.get("code") or "engine_unavailable")
        stderr = probe.diagnostics.get("stderr")
        return self._failure(
            code,
            "Bambu Studio failed its runtime version check.",
            stderr=str(stderr) if stderr else None,
        )

    def _probe_failure(
        self,
        code: str,
        *,
        stderr: str | None = None,
        engine_version: str | None = None,
    ) -> EngineProbe:
        diagnostics: dict[str, object] = {"code": code}
        if stderr:
            diagnostics["stderr"] = stderr
        return EngineProbe(
            engine_key=self.engine_key,
            engine_name=self.engine_name,
            available=False,
            engine_version=engine_version,
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
    def _discard_artifact(artifact_path: Path) -> None:
        try:
            artifact_path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _stderr(proc: subprocess.CompletedProcess[bytes], workspace: Path | None = None) -> str:
        stderr = proc.stderr
        value = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else str(stderr or "")
        if workspace is not None:
            value = value.replace(str(workspace), "[workspace]")
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
