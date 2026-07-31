from __future__ import annotations

import re
import subprocess
from decimal import Decimal
from pathlib import Path

from app.schemas.slice import SlicerStats

SLICER_PROFILES_DIR = Path(__file__).resolve().parents[2] / "slicer_profiles"
DEFAULT_SLICER_PROFILE = "bambu_a1.ini"
PRUSA_BED_SHAPES: dict[str, str] = {
    "bambu_a1": "0x0,256x0,256x256,0x256",
    "bambu_x1c": "0x0,256x0,256x256,0x256",
    "bambu_p1p": "0x0,256x0,256x256,0x256",
}

PLA_DENSITY_G_PER_CM3 = Decimal("1.24")


def _normalize_fill_density(value: object) -> str | None:
    """Return a PrusaSlicer-safe fill density percent, or ``None`` if unusable."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    has_percent = raw.endswith("%")
    raw_number = raw[:-1].strip() if has_percent else raw
    try:
        percent = Decimal(raw_number)
    except Exception:
        return None

    # Some callers and embedded 3MF settings use a 0-1 ratio. Treat it as a
    # percent ratio only when the source did not already include a percent sign.
    if not has_percent and Decimal("0") <= percent <= Decimal("1"):
        percent *= Decimal("100")

    if percent < 0:
        percent = Decimal("0")
    if percent > 100:
        percent = Decimal("100")

    normalized = f"{percent.quantize(Decimal('0.01')):f}".rstrip("0").rstrip(".")
    return f"{normalized}%"


def _slicer_profile_path(profile_name: str | None = None) -> Path:
    name = profile_name or DEFAULT_SLICER_PROFILE
    if not name.lower().endswith(".ini"):
        name = f"{name}.ini"
    path = SLICER_PROFILES_DIR / name
    if not path.exists():
        path = SLICER_PROFILES_DIR / DEFAULT_SLICER_PROFILE
    return path


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


def _parse_gcode_stats(gcode_path: str | Path, *, density: Decimal = PLA_DENSITY_G_PER_CM3) -> dict | None:
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

    grams_patterns = [
        ("total_filament_used_g", re.compile(r";\s*total filament used\s*\[g\]\s*=\s*([\d.]+)", re.IGNORECASE)),
        ("filament_used_g", re.compile(r";\s*filament used\s*\[g\]\s*=\s*([\d.]+)", re.IGNORECASE)),
    ]
    volume_pattern = re.compile(r";\s*filament used\s*\[cm3\]\s*=\s*([\d.]+)", re.IGNORECASE)
    cost_pattern = re.compile(r";\s*total filament cost\s*=\s*([\d.]+)", re.IGNORECASE)
    time_patterns = [
        (
            "estimated_printing_time_normal",
            re.compile(r";\s*estimated printing time\s*\(normal mode\)\s*=\s*(.+)", re.IGNORECASE),
        ),
        ("estimated_printing_time", re.compile(r";\s*estimated (?:printing|print) time\s*=\s*(.+)", re.IGNORECASE)),
        ("total_estimated_time", re.compile(r";\s*total estimated time\s*=\s*(.+)", re.IGNORECASE)),
        ("estimated_time", re.compile(r";\s*estimated time\s*=\s*(.+)", re.IGNORECASE)),
    ]
    layer_pattern = re.compile(r";\s*(?:total layers count|layer_count)\s*[:=]\s*(\d+)", re.IGNORECASE)
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


def slice_model(
    model_path: str,
    profile_name: str | None = None,
    center: str | None = "128,128",
    slicer_options: dict | None = None,
    preserve_orientation: bool | None = None,
) -> SlicerStats:
    from app.config import settings

    profile_path = _slicer_profile_path(profile_name)
    prusa_bin = settings.prusa_slicer_path

    try:
        check = subprocess.run(
            [prusa_bin, "--help-fff"],
            capture_output=True,
            timeout=10,
        )
        if check.returncode != 0:
            return SlicerStats(
                success=False,
                error="PrusaSlicer executable check failed.",
                profile_used=profile_path.name,
            )
    except FileNotFoundError:
        return SlicerStats(
            success=False,
            error="PrusaSlicer is not installed. Install it or set PRUSA_SLICER_PATH.",
            profile_used=profile_path.name,
        )
    except Exception as exc:
        return SlicerStats(
            success=False,
            error=f"PrusaSlicer check failed: {exc}",
            profile_used=profile_path.name,
        )

    output_path = str(Path(model_path).with_suffix(".gcode"))

    cmd = [
        prusa_bin,
        "--export-gcode",
        "--load",
        str(profile_path),
        "--output",
        output_path,
    ]
    options = slicer_options or {}
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
    fill_density = _normalize_fill_density(options.get("infill_percent"))
    if fill_density is not None:
        cmd.extend(["--fill-density", fill_density])
    if options.get("supports") in {"build_plate", "everywhere"}:
        cmd.extend(["--support-material", "1"])
        if options["supports"] == "build_plate":
            cmd.extend(["--support-material-buildplate-only", "1"])
    if options.get("nozzle_diameter") is not None:
        cmd.extend(["--nozzle-diameter", str(options["nozzle_diameter"])])
    if options.get("filament_density") is not None:
        cmd.extend(["--filament-density", str(options["filament_density"])])
    filament_type = options.get("filament_type") or options.get("material")
    if filament_type is not None:
        cmd.extend(["--filament-type", str(filament_type)])
    cmd.append(str(model_path))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return SlicerStats(
            success=False,
            error="PrusaSlicer timed out after 600s.",
            profile_used=profile_path.name,
        )
    except Exception as exc:
        return SlicerStats(
            success=False,
            error=f"PrusaSlicer execution failed: {exc}",
            profile_used=profile_path.name,
        )

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        return SlicerStats(
            success=False,
            error=f"PrusaSlicer exited with code {proc.returncode}. stderr: {stderr[:1000]}",
            profile_used=profile_path.name,
        )

    if not Path(output_path).exists():
        return SlicerStats(
            success=False,
            error="PrusaSlicer did not produce an output file.",
            profile_used=profile_path.name,
        )

    density = (
        Decimal(str(options.get("filament_density", "1.24")))
        if options.get("filament_density")
        else PLA_DENSITY_G_PER_CM3
    )
    stats = _parse_gcode_stats(output_path, density=density)
    if stats:
        try:
            gcode = Path(output_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            gcode = None
        return SlicerStats(
            success=True,
            filament_grams=stats["filament_grams"],
            print_minutes=stats["print_minutes"],
            profile_used=profile_path.name,
            stats=stats,
            gcode=gcode,
        )
    return SlicerStats(
        success=False,
        error="Could not parse filament/time from G-code output.",
        profile_used=profile_path.name,
    )
