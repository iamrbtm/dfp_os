"""Material density and default-temperature helpers (Issue 10).

Density resolution priority (highest wins): manual override -> embedded 3MF
value -> material defaults table. ``resolve_density`` returns the chosen value
along with a short source tag so callers (the analysis task, cost snapshot)
can record provenance.
"""

from __future__ import annotations

from decimal import Decimal

# Issue 10 — per-material defaults. Densities are g/cm^3; temps are Celsius.
MATERIAL_DEFAULTS: dict[str, dict[str, float]] = {
    "PLA": {"density": 1.24, "default_temp": 215},
    "PETG": {"density": 1.27, "default_temp": 240},
    "ABS": {"density": 1.04, "default_temp": 250},
    "ASA": {"density": 1.07, "default_temp": 260},
    "TPU": {"density": 1.21, "default_temp": 225},
}

# Fallback density when the material is unknown (matches PLA, the most common
# filament); callers still see source="default" so they know it is a fallback.
_UNKNOWN_DENSITY = Decimal("1.24")


def _normalize(material: str | None) -> str:
    return (material or "").strip().upper()


def resolve_density(
    material: str | None,
    *,
    embedded: float | str | None = None,
    manual: float | str | None = None,
) -> tuple[Decimal, str]:
    """Return ``(density_g_per_cm3, source)``.

    ``source`` is one of ``"manual"`` (caller-supplied value wins), ``"embedded"``
    (value read from a 3MF project file), or ``"default"`` (the ``MATERIAL_DEFAULTS``
    table). A unknown material falls back to the PLA density with source
    ``"default"``.
    """
    if manual is not None and str(manual) != "":
        return Decimal(str(manual)), "manual"
    if embedded is not None and str(embedded) != "":
        return Decimal(str(embedded)), "embedded"
    entry = MATERIAL_DEFAULTS.get(_normalize(material))
    if entry is not None:
        return Decimal(str(entry["density"])), "default"
    return _UNKNOWN_DENSITY, "default"


def material_default_temp(material: str | None) -> int | None:
    """Return the default print temperature for ``material`` or ``None``."""
    entry = MATERIAL_DEFAULTS.get(_normalize(material))
    return entry["default_temp"] if entry is not None else None


__all__ = ["MATERIAL_DEFAULTS", "resolve_density", "material_default_temp"]
