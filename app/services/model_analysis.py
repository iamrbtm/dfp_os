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
    name = profile_name or DEFAULT_SLICER_PROFILE
    path = SLICER_PROFILES_DIR / name
    if not path.exists() or not path.suffix == ".ini":
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
        mesh = trimesh.load_mesh(str(path))

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
    if center is not None:
        cmd.extend(["--center", center])
    options = slicer_options or {}
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

    grams_pattern = re.compile(r";\s*total filament used\s*\[g\]\s*=\s*([\d.]+)", re.IGNORECASE)
    volume_pattern = re.compile(r";\s*filament used\s*\[cm3\]\s*=\s*([\d.]+)", re.IGNORECASE)
    time_pattern = re.compile(
        r";\s*estimated (?:printing|print) time(?:\s*\(normal mode\))?\s*=\s*(.+)",
        re.IGNORECASE,
    )
    layer_pattern = re.compile(
        r";\s*(?:total layers count|layer_count)\s*[:=]\s*(\d+)", re.IGNORECASE
    )
    layer_count = None

    for line in lines:
        if not found_filament:
            m = grams_pattern.search(line)
            if m:
                val = Decimal(m.group(1))
                if val > 0:
                    filament_grams = val
                    found_filament = True

            m = volume_pattern.search(line)
            if m and not found_filament:
                val = Decimal(m.group(1))
                if val > 0:
                    filament_grams = (val * density).quantize(Decimal("0.01"))
                    found_filament = True

        if not found_time:
            m = time_pattern.search(line)
            if m:
                minutes = _parse_time_string(m.group(1).strip())
                if minutes is not None:
                    print_minutes = Decimal(str(minutes))
                    found_time = True
        m = layer_pattern.search(line)
        if m:
            layer_count = int(m.group(1))

    lines.close()

    if found_filament and found_time:
        return {
            "filament_grams": filament_grams,
            "print_minutes": print_minutes,
            "layer_count": layer_count,
        }
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

        mesh = trimesh.load_mesh(str(path))
        mesh.export(str(output_path), file_type="glb")
        return str(output_path)
    except Exception:
        return None
