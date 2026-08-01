from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.services.engines.base import (
    EngineArtifact,
    EngineFailure,
    EngineProbe,
    SliceOptions,
    safe_artifact_filename,
    sha256_file,
)
from app.services.engines.stats import (
    InvalidGcodeStatsError,
    _normalize_fill_density,
    _parse_gcode_stats,
    filament_density_from_options,
)

PRUSA_PROFILE_NAMES = {
    "bambu_a1": "bambu_a1.ini",
    "bambu_p1p": "bambu_p1p.ini",
    "bambu_x1c": "bambu_x1c.ini",
}


class PrusaEngine:
    engine_key = "prusa"
    engine_name = "PrusaSlicer"

    def __init__(
        self,
        executable: str,
        profiles_dir: Path,
        *,
        timeout: int = 600,
        probe_timeout: float = 4,
    ) -> None:
        self.executable = executable
        self.profiles_dir = Path(profiles_dir)
        self.timeout = timeout
        self.probe_timeout = probe_timeout
        self._engine_version = "unknown"

    def probe(self) -> EngineProbe:
        return self._probe(self.probe_timeout)

    def _probe(self, timeout: float) -> EngineProbe:
        if not all((self.profiles_dir / profile_name).is_file() for profile_name in PRUSA_PROFILE_NAMES.values()):
            return EngineProbe(
                engine_key=self.engine_key,
                engine_name=self.engine_name,
                available=False,
                diagnostics={"code": "profile_missing"},
            )
        try:
            proc = subprocess.run([self.executable, "--version"], capture_output=True, timeout=timeout)
        except FileNotFoundError:
            return EngineProbe(
                engine_key=self.engine_key,
                engine_name=self.engine_name,
                available=False,
                diagnostics={"code": "executable_missing"},
            )
        except subprocess.TimeoutExpired:
            return EngineProbe(
                engine_key=self.engine_key,
                engine_name=self.engine_name,
                available=False,
                diagnostics={"code": "probe_timeout"},
            )
        except Exception as exc:
            return EngineProbe(
                engine_key=self.engine_key,
                engine_name=self.engine_name,
                available=False,
                diagnostics={"code": "probe_failed", "error": str(exc)},
            )

        if proc.returncode != 0:
            version = self._version(getattr(proc, "stdout", None))
            if version == "unknown":
                try:
                    proc = subprocess.run([self.executable, "--help"], capture_output=True, timeout=timeout)
                except subprocess.TimeoutExpired:
                    return EngineProbe(
                        engine_key=self.engine_key,
                        engine_name=self.engine_name,
                        available=False,
                        diagnostics={"code": "probe_timeout"},
                    )
                except Exception as exc:
                    return EngineProbe(
                        engine_key=self.engine_key,
                        engine_name=self.engine_name,
                        available=False,
                        diagnostics={"code": "probe_failed", "error": str(exc)},
                    )
                version = self._version(getattr(proc, "stdout", None))
            if version == "unknown":
                return EngineProbe(
                    engine_key=self.engine_key,
                    engine_name=self.engine_name,
                    available=False,
                    diagnostics={"code": "probe_failed", "stderr": self._stderr(proc)},
                )
            self._engine_version = version
            return EngineProbe(
                engine_key=self.engine_key,
                engine_name=self.engine_name,
                available=True,
                engine_version=self._engine_version,
            )
        self._engine_version = self._version(getattr(proc, "stdout", None))
        if self._engine_version == "unknown":
            return EngineProbe(
                engine_key=self.engine_key,
                engine_name=self.engine_name,
                available=False,
                diagnostics={"code": "version_unrecognized"},
            )
        return EngineProbe(
            engine_key=self.engine_key,
            engine_name=self.engine_name,
            available=True,
            engine_version=self._engine_version,
        )

    def slice(self, model_path: Path, workspace: Path, options: SliceOptions) -> EngineArtifact | EngineFailure:
        profile_name = PRUSA_PROFILE_NAMES[options.printer]
        profile_path = self.profiles_dir / profile_name
        if not profile_path.exists():
            return EngineFailure(
                engine_key=self.engine_key,
                code="profile_missing",
                message=f"PrusaSlicer profile {profile_name} is unavailable.",
                fallback_eligible=True,
            )

        workspace.mkdir(parents=True, exist_ok=True)
        artifact_filename = f"{Path(safe_artifact_filename(model_path.name)).stem}.gcode"
        artifact_path = workspace / artifact_filename
        try:
            artifact_path.unlink(missing_ok=True)
        except OSError as exc:
            return self._failure("workspace_error", f"Could not prepare the G-code output path: {exc}")
        slice_timeout = float(self.timeout)
        if self._engine_version == "unknown":
            version_budget = min(float(self.probe_timeout), slice_timeout / 2)
            probe = self._probe(version_budget)
            if not probe.available:
                return self._failure(
                    str(probe.diagnostics.get("code") or "probe_failed"),
                    "PrusaSlicer failed its runtime version check.",
                )
            slice_timeout -= version_budget

        command = self._command(model_path, artifact_path, profile_path, options)
        try:
            proc = subprocess.run(command, capture_output=True, timeout=slice_timeout)
        except FileNotFoundError:
            return self._failure(
                "executable_missing", "PrusaSlicer is not installed. Install it or set PRUSA_SLICER_PATH."
            )
        except subprocess.TimeoutExpired:
            return self._failure("timeout", f"PrusaSlicer exceeded its {self.timeout}s engine budget.")
        except Exception as exc:
            return self._failure("execution_failed", f"PrusaSlicer execution failed: {exc}")

        if proc.returncode != 0:
            return self._failure(
                "execution_failed",
                f"PrusaSlicer exited with code {proc.returncode}.",
                stderr=self._stderr(proc),
            )
        if not artifact_path.exists():
            return self._failure("missing_output", "PrusaSlicer did not produce an output file.")

        try:
            stats = _parse_gcode_stats(artifact_path, density=filament_density_from_options(options.slicer_options))
        except InvalidGcodeStatsError:
            return self._failure("invalid_output", "G-code output contains malformed statistics.")
        if stats is None:
            return self._failure("missing_stats", "Could not parse filament/time from G-code output.")

        return EngineArtifact(
            engine_key=self.engine_key,
            engine_name=self.engine_name,
            engine_version=self._engine_version,
            artifact_path=artifact_path,
            artifact_filename=artifact_filename,
            artifact_media_type="text/x.gcode",
            artifact_size=artifact_path.stat().st_size,
            artifact_sha256=sha256_file(artifact_path),
            filament_grams=stats["filament_grams"],
            print_minutes=stats["print_minutes"],
            layer_count=stats["layer_count"],
            profile_ids={"printer": options.printer, "profile": profile_name},
            direct_print_eligible=False,
            estimate_only=True,
            diagnostics={"stats": stats},
        )

    def _command(self, model_path: Path, artifact_path: Path, profile_path: Path, options: SliceOptions) -> list[str]:
        values = options.slicer_options
        command = [
            self.executable,
            "--export-gcode",
            "--load",
            str(profile_path),
            "--output",
            str(artifact_path),
        ]
        center = values.get("center")
        if center is not None and not options.preserve_orientation:
            command.extend(["--center", str(center)])
        for key, flag in {
            "layer_height": "--layer-height",
            "perimeters": "--perimeters",
            "top_solid_layers": "--top-solid-layers",
            "bottom_solid_layers": "--bottom-solid-layers",
            "infill_pattern": "--fill-pattern",
            "brim_width": "--brim-width",
        }.items():
            if values.get(key) is not None:
                command.extend([flag, str(values[key])])
        fill_density = _normalize_fill_density(values.get("infill_percent"))
        if fill_density is not None:
            command.extend(["--fill-density", fill_density])
        if values.get("supports") in {"build_plate", "everywhere"}:
            command.extend(["--support-material", "1"])
            if values["supports"] == "build_plate":
                command.extend(["--support-material-buildplate-only", "1"])
        command.extend(["--nozzle-diameter", str(options.nozzle_diameter)])
        density = values.get("filament_density")
        if density is not None:
            command.extend(["--filament-density", str(density)])
        command.extend(["--filament-type", options.material, str(model_path)])
        return command

    def _failure(self, code: str, message: str, *, stderr: str | None = None) -> EngineFailure:
        diagnostics = {"stderr": stderr} if stderr else {}
        return EngineFailure(self.engine_key, code, message, fallback_eligible=True, diagnostics=diagnostics)

    @staticmethod
    def _stderr(proc: subprocess.CompletedProcess[bytes]) -> str:
        stderr = proc.stderr
        if isinstance(stderr, bytes):
            return stderr.decode("utf-8", errors="replace").strip()[:512]
        return str(stderr or "").strip()[:512]

    @staticmethod
    def _version(stdout: bytes | str | None) -> str:
        value = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else str(stdout or "")
        match = re.search(r"\d+(?:\.\d+)+", value)
        return match.group(0) if match else "unknown"
