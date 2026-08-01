from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.schemas.slice import SlicerStats
from app.services.engines.base import EngineArtifact, SliceOptions
from app.services.engines.prusa import PrusaEngine
from app.services.engines.stats import (
    PLA_DENSITY_G_PER_CM3,
    _normalize_fill_density,
    _parse_gcode_stats,
    _parse_time_string,
)

SLICER_PROFILES_DIR = Path(__file__).resolve().parents[2] / "slicer_profiles"
DEFAULT_SLICER_PROFILE = "bambu_a1.ini"
PRUSA_BED_SHAPES: dict[str, str] = {
    "bambu_a1": "0x0,256x0,256x256,0x256",
    "bambu_x1c": "0x0,256x0,256x256,0x256",
    "bambu_p1p": "0x0,256x0,256x256,0x256",
}


def _slicer_profile_path(profile_name: str | None = None) -> Path:
    name = profile_name or DEFAULT_SLICER_PROFILE
    if not name.lower().endswith(".ini"):
        name = f"{name}.ini"
    path = SLICER_PROFILES_DIR / name
    if not path.exists():
        path = SLICER_PROFILES_DIR / DEFAULT_SLICER_PROFILE
    return path


def slice_model(
    model_path: str,
    profile_name: str | None = None,
    center: str | None = "128,128",
    slicer_options: dict | None = None,
    preserve_orientation: bool | None = None,
) -> SlicerStats:
    """Slice through the legacy API while delegating to the Prusa engine adapter."""
    from app.config import settings

    source_path = Path(model_path)
    profile_path = _slicer_profile_path(profile_name)
    options = dict(slicer_options or {})
    options["center"] = center
    options.setdefault("model_filename", source_path.name)
    printer = profile_path.stem
    adapter_options = SliceOptions(
        printer=printer,
        nozzle_diameter=_legacy_nozzle(options),
        material=str(options.get("filament_type") or options.get("material") or "PLA"),
        model_suffix=source_path.suffix.lower(),
        slicer_options=options,
        preserve_orientation=bool(preserve_orientation),
    )
    engine = PrusaEngine(settings.prusa_slicer_path, SLICER_PROFILES_DIR)
    probe = engine.probe()
    if not probe.available:
        return SlicerStats(
            success=False,
            error=_probe_error(probe.diagnostics.get("code")),
            profile_used=profile_path.name,
        )

    result = engine.slice(source_path, source_path.parent / "slice-output", adapter_options)
    if not isinstance(result, EngineArtifact):
        error = result.message
        if stderr := result.diagnostics.get("stderr"):
            error = f"{error} stderr: {stderr}"
        return SlicerStats(success=False, error=error, profile_used=profile_path.name)
    try:
        gcode = result.artifact_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        gcode = None
    stats = result.diagnostics["stats"]
    return SlicerStats(
        success=True,
        filament_grams=result.filament_grams,
        print_minutes=result.print_minutes,
        profile_used=profile_path.name,
        stats=stats,
        gcode=gcode,
    )


def _legacy_nozzle(options: dict[object, object]) -> Decimal:
    try:
        return Decimal(str(options.get("nozzle_diameter", "0.4")))
    except Exception:
        return Decimal("0.4")


def _probe_error(code: object) -> str:
    if code == "executable_missing":
        return "PrusaSlicer is not installed. Install it or set PRUSA_SLICER_PATH."
    if code == "probe_failed":
        return "PrusaSlicer executable check failed."
    return "PrusaSlicer check failed."


__all__ = [
    "DEFAULT_SLICER_PROFILE",
    "PLA_DENSITY_G_PER_CM3",
    "PRUSA_BED_SHAPES",
    "SLICER_PROFILES_DIR",
    "_normalize_fill_density",
    "_parse_gcode_stats",
    "_parse_time_string",
    "_slicer_profile_path",
    "slice_model",
]
