from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import monotonic

from fastapi import Request

from app.config import settings
from app.services.engines.bambu import BambuEngine
from app.services.engines.bambu_profiles import BambuProfileError, BambuProfileResolver
from app.services.engines.base import EngineFailure, EngineProbe, SliceOptions, SlicerEngine
from app.services.engines.orchestrator import SlicerOrchestrator
from app.services.engines.prusa import PrusaEngine


def split_engine_timeouts(total_seconds: int) -> tuple[int, int]:
    if total_seconds < 2:
        raise ValueError("The total slice timeout must allow at least one second per engine.")
    return ((total_seconds + 1) // 2, total_seconds // 2)


class ReadinessProbeCache:
    def __init__(self, *, ttl_seconds: float, timeout_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._cached: dict[str, EngineProbe] | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def probe(self, engines: dict[str, SlicerEngine]) -> dict[str, EngineProbe]:
        now = monotonic()
        if self._cached is not None and now < self._expires_at:
            return dict(self._cached)
        async with self._lock:
            now = monotonic()
            if self._cached is not None and now < self._expires_at:
                return dict(self._cached)
            engine_items = list(engines.items())
            results = await asyncio.gather(
                *(self._probe_one(engine_key, engine) for engine_key, engine in engine_items)
            )
            self._cached = dict(zip((item[0] for item in engine_items), results, strict=True))
            self._expires_at = monotonic() + self.ttl_seconds
            return dict(self._cached)

    async def _probe_one(self, engine_key: str, engine: SlicerEngine) -> EngineProbe:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(engine.probe),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            return _unavailable_probe(engine_key, "probe_timeout")
        except Exception:
            return _unavailable_probe(engine_key, "probe_failed")


def _unavailable_probe(engine_key: str, code: str) -> EngineProbe:
    return EngineProbe(
        engine_key=engine_key,
        engine_name="Bambu Studio" if engine_key == "bambu" else "PrusaSlicer",
        available=False,
        diagnostics={"code": code},
    )


@dataclass(frozen=True)
class SlicerRuntime:
    engines: dict[str, SlicerEngine]
    orchestrator: SlicerOrchestrator
    admission: SliceAdmission
    readiness: ReadinessProbeCache


class SliceAdmission:
    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("The concurrent slice limit must be positive.")
        self.limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self._active >= self.limit:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            if self._active < 1:
                raise RuntimeError("Slice admission released without a matching acquisition.")
            self._active -= 1


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
def build_slicer_runtime() -> SlicerRuntime:
    bambu_timeout, prusa_timeout = split_engine_timeouts(settings.slice_timeout_seconds)
    try:
        resolver = BambuProfileResolver(Path(settings.bambu_profile_root))
        bambu: SlicerEngine = BambuEngine(
            settings.bambu_studio_path,
            resolver,
            timeout=bambu_timeout,
            probe_timeout=settings.readiness_timeout_seconds,
        )
    except BambuProfileError as exc:
        bambu = _UnavailableEngine("bambu", "Bambu Studio", exc.code)

    profiles_dir = Path(__file__).resolve().parents[2] / "slicer_profiles"
    prusa: SlicerEngine = PrusaEngine(
        settings.prusa_slicer_path,
        profiles_dir,
        timeout=prusa_timeout,
        probe_timeout=settings.readiness_timeout_seconds,
    )
    engines = {"bambu": bambu, "prusa": prusa}
    return SlicerRuntime(
        engines=engines,
        orchestrator=SlicerOrchestrator(engines, settings.engine_order),
        admission=SliceAdmission(settings.max_concurrent_slices),
        readiness=ReadinessProbeCache(
            ttl_seconds=settings.readiness_cache_ttl_seconds,
            timeout_seconds=settings.readiness_timeout_seconds,
        ),
    )


async def get_slicer_runtime(request: Request) -> SlicerRuntime:
    runtime = getattr(request.app.state, "slicer_runtime", None)
    if runtime is None:
        runtime = build_slicer_runtime()
    return runtime
