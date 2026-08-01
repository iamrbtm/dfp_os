from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from types import MappingProxyType

from app.services.engines.base import SUPPORTED_MATERIALS


BAMBU_PROFILE_MATRIX = {
    "bambu_a1": {
        "machine": "Bambu Lab A1 0.4 nozzle",
        "process": "0.20mm Standard @BBL A1",
        "filament": "Generic {material} @BBL A1",
    },
    "bambu_p1p": {
        "machine": "Bambu Lab P1P 0.4 nozzle",
        "process": "0.20mm Standard @BBL P1P",
        "filament": "Generic {material} @BBL P1P",
    },
    "bambu_x1c": {
        "machine": "Bambu Lab X1 Carbon 0.4 nozzle",
        "process": "0.20mm Standard @BBL X1C",
        "filament": "Generic {material}",
    },
}


class BambuProfileError(ValueError):
    """A stable failure while selecting or flattening pinned Bambu profiles."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedBambuProfiles:
    machine_path: Path
    process_path: Path
    filament_path: Path
    profile_ids: dict[str, str]


class BambuProfileResolver:
    """Resolve allowlisted Bambu presets into standalone per-request files."""

    def __init__(self, profile_root: Path) -> None:
        self.profile_root = Path(profile_root)
        self._profiles = self._build_index()
        self._flattened: Mapping[str, bytes] = MappingProxyType({})
        self._cache_lock = RLock()

    def resolve(self, printer_key: str, material: str, workspace: Path) -> ResolvedBambuProfiles:
        printer = str(printer_key).strip().lower()
        if printer not in BAMBU_PROFILE_MATRIX:
            raise BambuProfileError("unsupported_printer", "The requested Bambu printer profile is unsupported.")

        normalized_material = str(material).strip().upper()
        if normalized_material not in SUPPORTED_MATERIALS:
            raise BambuProfileError("unsupported_material", "The requested Bambu material profile is unsupported.")

        selected = BAMBU_PROFILE_MATRIX[printer]
        profile_ids = {
            "machine": selected["machine"],
            "process": selected["process"],
            "filament": selected["filament"].format(material=normalized_material),
        }

        request_workspace = Path(workspace)
        try:
            request_workspace.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BambuProfileError("workspace_unavailable", "Could not prepare the Bambu profile workspace.") from exc
        paths = {
            "machine": request_workspace / "machine.json",
            "process": request_workspace / "process.json",
            "filament": request_workspace / "filament.json",
        }
        for profile_type, path in paths.items():
            flattened = self._flatten(profile_ids[profile_type])
            try:
                path.write_text(
                    json.dumps(flattened, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                raise BambuProfileError("profile_write_failed", "Could not write a resolved Bambu profile.") from exc

        return ResolvedBambuProfiles(
            machine_path=paths["machine"],
            process_path=paths["process"],
            filament_path=paths["filament"],
            profile_ids=profile_ids,
        )

    def _build_index(self) -> Mapping[str, bytes]:
        if not self.profile_root.is_dir():
            raise BambuProfileError("profile_root_missing", "The configured Bambu profile root is unavailable.")

        profiles: dict[str, bytes] = {}
        for path in sorted(self.profile_root.rglob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise BambuProfileError("invalid_profile", f"Could not read a Bambu profile: {path.name}.") from exc
            if not isinstance(value, dict):
                continue
            name = value.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            if name in profiles:
                raise BambuProfileError("duplicate_profile", f"Bambu profile name is duplicated: {name}.")
            profiles[name] = self._serialize(value)
        return MappingProxyType(profiles)

    def _flatten(self, name: str, active: tuple[str, ...] = ()) -> dict[str, object]:
        with self._cache_lock:
            cached = self._flattened.get(name)
            if cached is not None:
                return json.loads(cached)
            if name in active:
                raise BambuProfileError("profile_cycle", f"Bambu profile inheritance contains a cycle at: {name}.")

            serialized_profile = self._profiles.get(name)
            if serialized_profile is None:
                raise BambuProfileError("profile_missing", f"Required Bambu profile is unavailable: {name}.")
            profile = json.loads(serialized_profile)

            next_active = (*active, name)
            flattened: dict[str, object] = {}
            parent = profile.get("inherits")
            if parent:
                if not isinstance(parent, str):
                    raise BambuProfileError("invalid_profile", f"Bambu profile has an invalid parent: {name}.")
                flattened.update(self._flatten(parent, next_active))

            includes = profile.get("include", [])
            if not isinstance(includes, list) or any(not isinstance(value, str) for value in includes):
                raise BambuProfileError("invalid_profile", f"Bambu profile has invalid includes: {name}.")
            for included_name in includes:
                flattened.update(self._flatten(included_name, next_active))

            flattened.update({key: value for key, value in profile.items() if key not in {"inherits", "include"}})
            serialized_flattened = self._serialize(flattened)
            self._flattened = MappingProxyType({**self._flattened, name: serialized_flattened})
            return json.loads(serialized_flattened)

    @staticmethod
    def _serialize(value: dict[str, object]) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
