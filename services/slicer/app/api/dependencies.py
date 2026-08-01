from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import settings
from app.services.engines.bambu import BambuEngine
from app.services.engines.bambu_profiles import BambuProfileError, BambuProfileResolver
from app.services.engines.base import EngineFailure, EngineProbe, SliceOptions, SlicerEngine
from app.services.engines.orchestrator import SlicerOrchestrator
from app.services.engines.prusa import PrusaEngine


@dataclass(frozen=True)
class SlicerRuntime:
    engines: dict[str, SlicerEngine]
    orchestrator: SlicerOrchestrator


class _UnavailableEngine:
    def __init__(self, engine_key: str, engine_name: str, error_code: str) -> None:
        self.engine_key = engine_key
        self.engine_name = engine_name
        self.error_code = error_code

    def probe(self) -> EngineProbe:
        return EngineProbe(
            engine_key=self.engine_key,
            engine_name=self.engine_name,
            available=False,
            diagnostics={"code": self.error_code},
        )

    def slice(self, model_path: Path, workspace: Path, options: SliceOptions) -> EngineFailure:
        return EngineFailure(
            engine_key=self.engine_key,
            code=self.error_code,
            message=f"{self.engine_name} is unavailable.",
            fallback_eligible=True,
        )


@lru_cache(maxsize=1)
def get_slicer_runtime() -> SlicerRuntime:
    try:
        resolver = BambuProfileResolver(Path(settings.bambu_profile_root))
        bambu: SlicerEngine = BambuEngine(
            settings.bambu_studio_path,
            resolver,
            timeout=settings.slice_timeout_seconds,
        )
    except BambuProfileError as exc:
        bambu = _UnavailableEngine("bambu", "Bambu Studio", exc.code)

    profiles_dir = Path(__file__).resolve().parents[2] / "slicer_profiles"
    prusa: SlicerEngine = PrusaEngine(settings.prusa_slicer_path, profiles_dir)
    engines = {"bambu": bambu, "prusa": prusa}
    return SlicerRuntime(
        engines=engines,
        orchestrator=SlicerOrchestrator(engines, settings.engine_order),
    )
