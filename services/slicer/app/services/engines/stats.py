from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

PLA_DENSITY_G_PER_CM3 = Decimal("1.24")


class InvalidGcodeStatsError(ValueError):
    """Raised when a G-code statistics comment has an invalid numeric value."""


def _parse_decimal_comment(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidGcodeStatsError("G-code statistics contain an invalid numeric value.") from exc
    if not parsed.is_finite():
        raise InvalidGcodeStatsError("G-code statistics contain an invalid numeric value.")
    return parsed


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
    except InvalidOperation, ValueError:
        return None

    if not has_percent and Decimal("0") <= percent <= Decimal("1"):
        percent *= Decimal("100")

    if percent < 0:
        percent = Decimal("0")
    if percent > 100:
        percent = Decimal("100")

    normalized = f"{percent.quantize(Decimal('0.01')):f}".rstrip("0").rstrip(".")
    return f"{normalized}%"


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
    except OSError:
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
        (
            "total_filament_used_g",
            re.compile(r";\s*total filament used\s*\[g\]\s*[:=]\s*([\d.]+)", re.IGNORECASE),
        ),
        (
            "total_filament_weight_g",
            re.compile(r";\s*total filament weight\s*\[g\]\s*[:=]\s*([\d.]+)", re.IGNORECASE),
        ),
        ("filament_used_g", re.compile(r";\s*filament used\s*\[g\]\s*[:=]\s*([\d.]+)", re.IGNORECASE)),
    ]
    volume_pattern = re.compile(r";\s*filament used\s*\[cm3\]\s*=\s*([\d.]+)", re.IGNORECASE)
    cost_pattern = re.compile(r";\s*total filament cost\s*=\s*([\d.]+)", re.IGNORECASE)
    time_patterns = [
        (
            "estimated_printing_time_normal",
            re.compile(r";\s*estimated printing time\s*\(normal mode\)\s*=\s*(.+)", re.IGNORECASE),
        ),
        ("estimated_printing_time", re.compile(r";\s*estimated (?:printing|print) time\s*=\s*(.+)", re.IGNORECASE)),
        ("total_estimated_time", re.compile(r";\s*total estimated time\s*[:=]\s*(.+)", re.IGNORECASE)),
        ("estimated_time", re.compile(r";\s*estimated time\s*=\s*(.+)", re.IGNORECASE)),
    ]
    layer_pattern = re.compile(
        r";\s*(?:total layers count|total layer number|layer_count)\s*[:=]\s*(\d+)",
        re.IGNORECASE,
    )
    layer_count = None

    with lines:
        for line in lines:
            if not found_filament:
                for source_name, pattern in grams_patterns:
                    match = pattern.search(line)
                    if match:
                        value = _parse_decimal_comment(match.group(1))
                        if value > 0:
                            filament_grams = value
                            filament_source_pattern = source_name
                            found_filament = True
                            break
                if not found_filament:
                    match = volume_pattern.search(line)
                    if match:
                        value = _parse_decimal_comment(match.group(1))
                        if value > 0:
                            filament_grams = (value * density).quantize(Decimal("0.01"))
                            filament_source_pattern = "filament_used_cm3"
                            found_filament = True

            if cost_source_pattern is None:
                match = cost_pattern.search(line)
                if match:
                    filament_cost = _parse_decimal_comment(match.group(1))
                    cost_source_pattern = "total_filament_cost"

            if not found_time:
                for source_name, pattern in time_patterns:
                    match = pattern.search(line)
                    if match:
                        minutes = _parse_time_string(match.group(1).strip())
                        if minutes is not None:
                            print_minutes = Decimal(str(minutes))
                            time_source_pattern = source_name
                            found_time = True
                            break
            match = layer_pattern.search(line)
            if match:
                layer_count = int(match.group(1))

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


def filament_density_from_options(options: dict[str, object]) -> Decimal:
    value = options.get("filament_density")
    if value is None or value == "":
        return PLA_DENSITY_G_PER_CM3
    try:
        density = Decimal(str(value))
    except InvalidOperation, ValueError:
        return PLA_DENSITY_G_PER_CM3
    return density if density.is_finite() and density > 0 else PLA_DENSITY_G_PER_CM3
