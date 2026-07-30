from __future__ import annotations

import os
import json
import re
import subprocess
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

SLICER_PROFILES_DIR = Path(__file__).resolve().parent.parent / "slicer_profiles"

DEFAULT_SLICER_PROFILE = "bambu_a1.ini"
PRINTER_BUILD_VOLUMES: dict[str, dict[str, float]] = {
    "bambu_a1": {"x": 256, "y": 256, "z": 256},
    "bambu_x1c": {"x": 256, "y": 256, "z": 256},
    "bambu_p1p": {"x": 256, "y": 256, "z": 256},
}
PRUSA_BED_SHAPES: dict[str, str] = {
    "bambu_a1": "0x0,256x0,256x256,0x256",
    "bambu_x1c": "0x0,256x0,256x256,0x256",
    "bambu_p1p": "0x0,256x0,256x256,0x256",
}

# Issue 8 — quotable vs preview-only formats. Quotable formats can be sliced and
# costed; preview-only formats are converted to GLB for the viewer but are not
# sliced (the upload route skips slicing for these).
QUOTABLE_FORMATS: frozenset[str] = frozenset({".stl", ".3mf", ".obj"})
PREVIEW_ONLY_FORMATS: frozenset[str] = frozenset({".glb", ".gltf"})


def is_quotable_format(path: str | Path) -> bool:
    """Return ``True`` if ``path`` is a slicable, costable model format."""
    return Path(path).suffix.lower() in QUOTABLE_FORMATS


def task_envelope(success: bool, data: dict | None = None, error: str = "") -> dict:
    """Standard Celery task result envelope (Issue 5).

    The integrator's ``/task-status`` route reads ``result["success"]`` and then
    pulls the task-specific keys from ``result["data"]``. Existing task payloads
    are nested inside ``data`` so callers keep working.
    """
    return {"success": success, "data": data or {}, "error": error}


def ensure_slicer_profiles_dir() -> Path:
    """Create the slicer profiles directory if missing (Issue 23/49). No-op if it exists."""
    SLICER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return SLICER_PROFILES_DIR


@dataclass
class ValidationResult:
    volume_mm3: float = 0.0
    surface_area_mm2: float = 0.0
    bounding_box: dict[str, float] = field(default_factory=dict)
    triangle_count: int = 0
    is_watertight: bool = False
    printer_fit: bool = True
    scale_warning: str | None = None
    format_detected: str = ""
    error: str | None = None
    success: bool = False


@dataclass
class SlicerResult:
    filament_grams: Decimal = Decimal("0")
    print_minutes: Decimal = Decimal("0")
    profile_used: str = ""
    error: str | None = None
    success: bool = False
    stats: dict = field(default_factory=dict)


@dataclass
class ModelAnalysisResult:
    validation: ValidationResult | None = None
    slicer: SlicerResult | None = None
    error: str | None = None
    success: bool = False


def slicer_profile_path(profile_name: str | None = None) -> Path:
    # Issue 23/49 — accept a bare name like "bambu_a1" (no .ini) by appending
    # the suffix when it is missing before resolving against the profiles dir.
    name = profile_name or DEFAULT_SLICER_PROFILE
    if not name.lower().endswith(".ini"):
        name = f"{name}.ini"
    path = SLICER_PROFILES_DIR / name
    if not path.exists():
        path = SLICER_PROFILES_DIR / DEFAULT_SLICER_PROFILE
    return path


def extract_3mf_slicer_settings(file_path: str | Path) -> dict:
    """Extract common Prusa/Bambu/Orca project settings from a 3MF archive."""
    path = Path(file_path)
    if path.suffix.lower() != ".3mf" or not zipfile.is_zipfile(path):
        return {}

    wanted = {
        "layer_height",
        "perimeters",
        "top_solid_layers",
        "bottom_solid_layers",
        "fill_density",
        "fill_pattern",
        "brim_width",
        "nozzle_diameter",
        "filament_density",
        "filament_type",
        "support_material",
        "support_material_buildplate_only",
    }
    extracted: dict = {}
    with zipfile.ZipFile(path) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.lower().endswith((".config", ".ini"))
            or "project_settings" in name.lower()
        ]
        for name in candidates:
            text = archive.read(name).decode("utf-8", errors="replace")
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                for key in wanted:
                    if key in payload:
                        extracted[key] = payload[key]
            for line in text.splitlines():
                if "=" not in line:
                    continue
                key, value = (part.strip() for part in line.split("=", 1))
                if key in wanted:
                    extracted[key] = value
    return extracted


def _coerce_to_mesh(loaded: object) -> tuple[object, str | None]:
    """Merge a trimesh Scene into a single mesh (Issue 11).

    ``trimesh.load_mesh`` returns a ``Scene`` for multi-mesh files (many 3MF/OBJ
    exports). Slicing and geometry reads need one mesh, so concatenate all of
    the scene's geometries. Returns ``(mesh, warning)``; on merge failure the
    warning is set and the mesh is ``None`` so the caller can fall back to
    approximate/zero values rather than crashing.
    """
    if hasattr(loaded, "geometry") and getattr(loaded, "geometry", None):
        try:
            import trimesh

            merged = trimesh.util.concatenate(list(loaded.geometry.values()))
            return merged, None
        except Exception as exc:  # pragma: no cover - defensive merge failure
            return None, f"Scene merge failed: {exc}"
    return loaded, None


def apply_scale(mesh_or_path: object, scale_percent: float | int | str | None) -> object:
    """Apply ``scale_percent`` to a mesh (or a path to one) and return the mesh.

    ``scale_percent`` of 100 leaves the geometry unchanged; 200 doubles it. The
    returned mesh is scaled in place — callers pass it to the slicer and to
    geometry reads so volume/grams/time reflect the scaled size (Issue 9/30).

    Scale is applied BEFORE slicing; copies divides plate cost for per-unit
    cost (see the analysis task).
    """
    import trimesh

    if isinstance(mesh_or_path, (str, Path)):
        loaded = trimesh.load_mesh(str(mesh_or_path))
        loaded, _ = _coerce_to_mesh(loaded)
    else:
        loaded = mesh_or_path

    if loaded is None or scale_percent is None:
        return loaded
    try:
        factor = float(Decimal(str(scale_percent)) / Decimal("100"))
    except Exception:
        return loaded
    if factor and factor != 1.0:
        loaded = loaded.apply_scale(factor)
    return loaded


def validate_model_file(file_path: str | Path) -> ValidationResult:
    result = ValidationResult()

    path = Path(file_path)
    if not path.exists():
        result.error = f"File not found: {path}"
        return result

    ext = path.suffix.lower()
    result.format_detected = ext

    try:
        import trimesh
    except ImportError:
        result.error = "trimesh is not installed. Cannot validate 3D models."
        return result

    try:
        loaded = trimesh.load_mesh(str(path))
        # Issue 11 — merge multi-mesh Scenes before reading geometry.
        mesh, merge_warning = _coerce_to_mesh(loaded)
        if merge_warning:
            result.scale_warning = merge_warning
        if mesh is None:
            # Merge failed: continue with approximate/zero values rather than crash.
            result.success = True
            return result

        result.volume_mm3 = float(mesh.volume) if mesh.volume else 0.0
        result.surface_area_mm2 = float(mesh.area) if mesh.area else 0.0
        result.triangle_count = (
            int(mesh.faces.shape[0]) if hasattr(mesh, "faces") and mesh.faces is not None else 0
        )

        try:
            result.is_watertight = bool(mesh.is_watertight)
        except Exception:
            result.is_watertight = False

        if hasattr(mesh, "bounds") and mesh.bounds is not None:
            bounds = mesh.bounds
            dims = {
                "min_x": float(bounds[0][0]),
                "min_y": float(bounds[0][1]),
                "min_z": float(bounds[0][2]),
                "max_x": float(bounds[1][0]),
                "max_y": float(bounds[1][1]),
                "max_z": float(bounds[1][2]),
                "width_mm": float(bounds[1][0] - bounds[0][0]),
                "depth_mm": float(bounds[1][1] - bounds[0][1]),
                "height_mm": float(bounds[1][2] - bounds[0][2]),
            }
            result.bounding_box = dims

            width = dims["width_mm"]
            depth = dims["depth_mm"]
            height = dims["height_mm"]

            max_dim = max(width, depth, height)
            if max_dim > 0 and max_dim < 10:
                result.scale_warning = (
                    f"Model appears to be in inches (largest dimension {max_dim:.2f} mm). "
                    f"Expected ~{max_dim * 25.4:.0f} mm if scaled to mm."
                )

        result.printer_fit = True
        for printer_key, vol in PRINTER_BUILD_VOLUMES.items():
            bb = result.bounding_box
            if bb and (
                bb.get("width_mm", 0) > vol["x"]
                or bb.get("depth_mm", 0) > vol["y"]
                or bb.get("height_mm", 0) > vol["z"]
            ):
                result.printer_fit = False
                break

        result.success = True

    except Exception as exc:
        result.error = f"Model validation failed: {exc}"

    return result


def slice_with_prusaslicer(
    model_path: str | Path,
    *,
    profile_name: str | None = None,
    output_path: str | Path | None = None,
    center: str | None = "128,128",
    slicer_options: dict | None = None,
    preserve_orientation: bool | None = None,
) -> SlicerResult:
    result = SlicerResult()

    model_path = Path(model_path)
    if not model_path.exists():
        result.error = f"Model file not found: {model_path}"
        return result

    profile_path = slicer_profile_path(profile_name)
    result.profile_used = profile_path.name

    if output_path is None:
        output_path = model_path.with_suffix(".gcode")

    prusa_bin = os.environ.get("PRUSA_SLICER_PATH", "prusa-slicer")

    try:
        check = subprocess.run(
            [prusa_bin, "--help-fff"],
            capture_output=True,
            timeout=10,
        )
        if check.returncode != 0:
            result.error = "PrusaSlicer executable check failed."
            return result
    except FileNotFoundError:
        result.error = "PrusaSlicer is not installed. Install it or set PRUSA_SLICER_PATH."
        return result
    except Exception as exc:
        result.error = f"PrusaSlicer check failed: {exc}"
        return result

    cmd = [
        prusa_bin,
        "--export-gcode",
        "--load",
        str(profile_path),
        "--output",
        str(output_path),
    ]
    options = slicer_options or {}
    # Issue 29/31 — preserve_orientation skips --center so the model keeps its
    # original placement. The retry path already passes center=None; threading
    # preserve_orientation here ensures the FIRST slice also omits --center.
    if center is not None and not preserve_orientation:
        cmd.extend(["--center", center])
    cli_values = {
        "layer_height": "--layer-height",
        "perimeters": "--perimeters",
        "top_solid_layers": "--top-solid-layers",
        "bottom_solid_layers": "--bottom-solid-layers",
        "infill_pattern": "--fill-pattern",
        "brim_width": "--brim-width",
    }
    for key, flag in cli_values.items():
        if options.get(key) is not None:
            cmd.extend([flag, str(options[key])])
    if options.get("infill_percent") is not None:
        cmd.extend(["--fill-density", f"{options['infill_percent']}%"])
    if options.get("supports") in {"build_plate", "everywhere"}:
        cmd.extend(["--support-material", "1"])
        if options["supports"] == "build_plate":
            cmd.extend(["--support-material-buildplate-only", "1"])
    # Issue 29/31 — nozzle / filament options added conditionally.
    if options.get("nozzle_diameter") is not None:
        cmd.extend(["--nozzle-diameter", str(options["nozzle_diameter"])])
    if options.get("filament_density") is not None:
        cmd.extend(["--filament-density", str(options["filament_density"])])
    filament_type = options.get("filament_type") or options.get("material")
    if filament_type is not None:
        cmd.extend(["--filament-type", str(filament_type)])
    # multicolor: (metadata only — not supported by slicer integration). The
    # wipe-tower flag is not exposed by PrusaSlicer's CLI, so this is a no-op.
    cmd.append(str(model_path))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        result.error = "PrusaSlicer timed out after 600s."
        return result
    except Exception as exc:
        result.error = f"PrusaSlicer execution failed: {exc}"
        return result

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        result.error = (
            f"PrusaSlicer exited with code {proc.returncode}. " f"stderr: {stderr[:1000]}"
        )
        return result

    if not Path(output_path).exists():
        result.error = "PrusaSlicer did not produce an output file."
        return result

    stats = _parse_gcode_stats(
        output_path, density=Decimal(str(options.get("filament_density", "1.24")))
    )
    if stats:
        result.filament_grams = stats["filament_grams"]
        result.print_minutes = stats["print_minutes"]
        result.stats = stats
        result.success = True
    else:
        result.error = "Could not parse filament/time from G-code output."
        return result

    return result


PLA_DENSITY_G_PER_CM3 = Decimal("1.24")


def _parse_gcode_stats(
    gcode_path: str | Path, *, density: Decimal = PLA_DENSITY_G_PER_CM3
) -> dict | None:
    path = Path(gcode_path)
    if not path.exists():
        return None

    try:
        lines = path.open("r", encoding="utf-8", errors="replace")
    except Exception:
        return None

    filament_grams = Decimal("0")
    print_minutes = Decimal("0")
    found_filament = False
    found_time = False
    filament_source_pattern: str | None = None
    time_source_pattern: str | None = None
    filament_cost: Decimal | None = None
    cost_source_pattern: str | None = None

    # Issue 12 — grams patterns across Prusa/Bambu/Orca. Order matters: the
    # explicit "total filament used [g]" wins, then Bambu's "filament used [g]",
    # then the cm3 volume fallback (converted with the chosen density).
    grams_patterns: list[tuple[str, re.Pattern[str]]] = [
        ("total_filament_used_g", re.compile(r";\s*total filament used\s*\[g\]\s*=\s*([\d.]+)", re.IGNORECASE)),
        ("filament_used_g", re.compile(r";\s*filament used\s*\[g\]\s*=\s*([\d.]+)", re.IGNORECASE)),
    ]
    volume_pattern = re.compile(r";\s*filament used\s*\[cm3\]\s*=\s*([\d.]+)", re.IGNORECASE)
    cost_pattern = re.compile(r";\s*total filament cost\s*=\s*([\d.]+)", re.IGNORECASE)
    # Time patterns across slicers; first match wins per line.
    time_patterns: list[tuple[str, re.Pattern[str]]] = [
        ("estimated_printing_time_normal", re.compile(
            r";\s*estimated printing time\s*\(normal mode\)\s*=\s*(.+)", re.IGNORECASE)),
        ("estimated_printing_time", re.compile(
            r";\s*estimated (?:printing|print) time\s*=\s*(.+)", re.IGNORECASE)),
        ("total_estimated_time", re.compile(
            r";\s*total estimated time\s*=\s*(.+)", re.IGNORECASE)),
        ("estimated_time", re.compile(
            r";\s*estimated time\s*=\s*(.+)", re.IGNORECASE)),
    ]
    layer_pattern = re.compile(
        r";\s*(?:total layers count|layer_count)\s*[:=]\s*(\d+)", re.IGNORECASE
    )
    layer_count = None

    for line in lines:
        if not found_filament:
            for source_name, pattern in grams_patterns:
                m = pattern.search(line)
                if m:
                    val = Decimal(m.group(1))
                    if val > 0:
                        filament_grams = val
                        filament_source_pattern = source_name
                        found_filament = True
                        break

            if not found_filament:
                m = volume_pattern.search(line)
                if m:
                    val = Decimal(m.group(1))
                    if val > 0:
                        filament_grams = (val * density).quantize(Decimal("0.01"))
                        filament_source_pattern = "filament_used_cm3"
                        found_filament = True

        if cost_source_pattern is None:
            m = cost_pattern.search(line)
            if m:
                filament_cost = Decimal(m.group(1))
                cost_source_pattern = "total_filament_cost"

        if not found_time:
            for source_name, pattern in time_patterns:
                m = pattern.search(line)
                if m:
                    minutes = _parse_time_string(m.group(1).strip())
                    if minutes is not None:
                        print_minutes = Decimal(str(minutes))
                        time_source_pattern = source_name
                        found_time = True
                        break
        m = layer_pattern.search(line)
        if m:
            layer_count = int(m.group(1))

    lines.close()

    if found_filament and found_time:
        stats: dict = {
            "filament_grams": filament_grams,
            "print_minutes": print_minutes,
            "layer_count": layer_count,
            "filament_source_pattern": filament_source_pattern,
            "time_source_pattern": time_source_pattern,
        }
        if filament_cost is not None:
            stats["filament_cost"] = filament_cost
            stats["cost_source_pattern"] = cost_source_pattern
        return stats
    return None


def _parse_time_string(time_str: str) -> float | None:
    total_minutes = 0.0

    d_match = re.search(r"(\d+)\s*d", time_str)
    h_match = re.search(r"(\d+)\s*h", time_str)
    m_match = re.search(r"(\d+)\s*m(?!\s*s)", time_str)
    s_match = re.search(r"(\d+)\s*s", time_str)

    if d_match:
        total_minutes += int(d_match.group(1)) * 1440
    if h_match:
        total_minutes += int(h_match.group(1)) * 60
    if m_match:
        total_minutes += int(m_match.group(1))
    if s_match:
        total_minutes += int(s_match.group(1)) / 60.0

    if d_match or h_match or m_match or s_match:
        return round(total_minutes, 2)
    return None


def convert_to_glb(file_path: str | Path, output_path: str | Path | None = None) -> str | None:
    path = Path(file_path)
    if not path.exists():
        return None

    ext = path.suffix.lower()
    if ext == ".glb":
        return str(path)

    if output_path is None:
        output_path = path.with_suffix(".glb")

    try:
        import trimesh

        loaded = trimesh.load_mesh(str(path))
        # Issue 11 — merge multi-mesh Scenes before exporting to GLB.
        mesh, merge_warning = _coerce_to_mesh(loaded)
        if mesh is None:
            return None
        mesh.export(str(output_path), file_type="glb")
        return str(output_path)
    except Exception:
        return None
