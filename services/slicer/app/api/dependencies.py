from __future__ import annotations

import asyncio
import concurrent.futures
import functools
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import Any, Callable, TypeVar

from fastapi import Request

from app.config import settings
from app.services.engines.bambu import BambuEngine
from app.services.engines.bambu_profiles import BambuProfileError, BambuProfileResolver
from app.services.engines.base import EngineFailure, EngineProbe, SliceOptions, SlicerEngine
from app.services.engines.orchestrator import SlicerOrchestrator
from app.services.engines.prusa import PrusaEngine

_ResultT = TypeVar("_ResultT")


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
    jobs: SliceJobManager
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


class SliceJobLease:
    def __init__(self, manager: SliceJobManager) -> None:
        self._manager = manager
        self._worker: asyncio.Task[Any] | None = None
        self._released = False

    async def run(self, function: Callable[..., _ResultT], *args: object, **kwargs: object) -> _ResultT:
        if self._released or self._worker is not None:
            raise RuntimeError("Slice job lease cannot start another worker.")
        worker = self._manager._submit(function, *args, **kwargs)
        self._worker = worker
        try:
            return await self._manager._wait_for_worker(worker)
        finally:
            self._worker = None

    async def release(self) -> None:
        if self._released:
            return
        if self._worker is not None:
            await self._manager._wait_for_worker(self._worker)
        release_task = asyncio.create_task(self._manager.admission.release())
        try:
            await self._manager._wait_without_abandoning(release_task)
        finally:
            if release_task.done() and not release_task.cancelled() and release_task.exception() is None:
                self._released = True


class SliceJobManager:
    """Own slice admission and retain worker tasks through request cancellation."""

    def __init__(
        self,
        admission: SliceAdmission,
        *,
        executor: concurrent.futures.Executor | None = None,
    ) -> None:
        self.admission = admission
        self._executor = executor
        self._jobs: set[asyncio.Task[Any]] = set()

    async def try_acquire(self) -> SliceJobLease | None:
        if not await self.admission.try_acquire():
            return None
        return SliceJobLease(self)

    def _submit(
        self,
        function: Callable[..., _ResultT],
        *args: object,
        **kwargs: object,
    ) -> asyncio.Task[_ResultT]:
        async def invoke() -> _ResultT:
            if self._executor is None:
                return await asyncio.to_thread(function, *args, **kwargs)
            loop = asyncio.get_running_loop()
            call = functools.partial(function, *args, **kwargs)
            return await loop.run_in_executor(self._executor, call)

        task = asyncio.create_task(invoke())
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)
        return task

    async def _wait_for_worker(self, task: asyncio.Task[_ResultT]) -> _ResultT:
        return await self._wait_without_abandoning(task)

    async def _wait_without_abandoning(self, task: asyncio.Task[_ResultT]) -> _ResultT:
        cancellation: asyncio.CancelledError | None = None
        while not task.done():
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError as exc:
                cancellation = cancellation or exc
        if cancellation is not None:
            if not task.cancelled():
                task.exception()
            raise cancellation
        return task.result()

    async def shutdown(self) -> None:
        cancellation: asyncio.CancelledError | None = None
        while self._jobs:
            workers = tuple(self._jobs)
            for worker in workers:
                try:
                    await self._wait_without_abandoning(worker)
                except asyncio.CancelledError as exc:
                    cancellation = cancellation or exc
                except Exception:
                    pass
            await asyncio.sleep(0)
        if cancellation is not None:
            raise cancellation


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
    admission = SliceAdmission(settings.max_concurrent_slices)
    return SlicerRuntime(
        engines=engines,
        orchestrator=SlicerOrchestrator(engines, settings.engine_order),
        admission=admission,
        jobs=SliceJobManager(admission),
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
