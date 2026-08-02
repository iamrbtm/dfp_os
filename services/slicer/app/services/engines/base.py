from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePath, PureWindowsPath
from typing import Protocol

SUPPORTED_PRINTERS = frozenset({"bambu_a1", "bambu_p1p", "bambu_x1c"})
SUPPORTED_MATERIALS = frozenset({"PLA", "PETG", "ABS", "ASA", "TPU"})
SUPPORTED_MODEL_SUFFIXES = frozenset({".stl", ".3mf", ".obj"})


class RequestValidationError(ValueError):
    """A terminal request error that must not trigger an engine fallback."""

    fallback_eligible = False

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class SliceOptions:
    printer: str
    nozzle_diameter: Decimal
    material: str
    model_suffix: str
    slicer_options: dict[str, object]
    preserve_orientation: bool

    @classmethod
    def from_request(
        cls,
        profile_name: str | None,
        slicer_options: dict[str, object] | None,
        preserve_orientation: bool | None,
    ) -> SliceOptions:
        options = dict(slicer_options or {})
        printer = (profile_name or "bambu_a1").strip().lower()
        if printer.endswith(".ini"):
            printer = printer[:-4]
        if printer not in SUPPORTED_PRINTERS:
            raise RequestValidationError("unsupported_printer", "The requested printer profile is unsupported.")

        try:
            nozzle_diameter = Decimal(str(options.get("nozzle_diameter", "0.4")))
        except InvalidOperation, ValueError:
            raise RequestValidationError("invalid_nozzle", "The nozzle diameter must be a decimal value.") from None
        if nozzle_diameter != Decimal("0.4"):
            raise RequestValidationError("unsupported_nozzle", "Only a 0.4 mm nozzle is supported.")

        material = str(options.get("material") or options.get("filament_type") or "PLA").strip().upper()
        if material not in SUPPORTED_MATERIALS:
            raise RequestValidationError("unsupported_material", "The requested material is unsupported.")

        model_filename = str(options.get("model_filename") or options.get("model_file") or "")
        model_suffix = PurePath(PureWindowsPath(model_filename).name).suffix.lower()
        if model_suffix not in SUPPORTED_MODEL_SUFFIXES:
            raise RequestValidationError("unsupported_model_suffix", "The uploaded model file type is unsupported.")

        return cls(
            printer=printer,
            nozzle_diameter=nozzle_diameter,
            material=material,
            model_suffix=model_suffix,
            slicer_options=options,
            preserve_orientation=bool(preserve_orientation),
        )


@dataclass(frozen=True)
class EngineProbe:
    engine_key: str
    engine_name: str
    available: bool
    engine_version: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineArtifact:
    engine_key: str
    engine_name: str
    engine_version: str
    artifact_path: Path
    artifact_filename: str
    artifact_media_type: str
    artifact_size: int
    artifact_sha256: str
    filament_grams: Decimal
    print_minutes: Decimal
    layer_count: int | None
    profile_ids: dict[str, str]
    direct_print_eligible: bool
    estimate_only: bool
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineFailure:
    engine_key: str
    code: str
    message: str
    fallback_eligible: bool
    diagnostics: dict[str, object] = field(default_factory=dict)


class SlicerEngine(Protocol):
    def probe(self) -> EngineProbe: ...

    def slice(self, model_path: Path, workspace: Path, options: SliceOptions) -> EngineArtifact | EngineFailure: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_artifact_filename(value: str) -> str:
    """Return a portable basename suitable for a generated artifact."""
    basename = PurePath(PureWindowsPath(value).name).name
    safe_value = re.sub(r"[^A-Za-z0-9._-]+", "-", basename).strip(".-")
    return safe_value or "artifact"
