from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Sequence

from app.services.engines.base import (
    EngineArtifact,
    EngineFailure,
    RequestValidationError,
    SliceOptions,
    SlicerEngine,
)


DEFAULT_ENGINE_ORDER = ("bambu", "prusa")
MAX_PUBLIC_FAILURE_MESSAGE_CHARS = 512
_ENGINE_NAMES = {"bambu": "Bambu Studio", "prusa": "PrusaSlicer"}
_PUBLIC_FAILURE_SUFFIXES = {
    "archive_limit_exceeded": "output exceeded a safety limit.",
    "duplicate_profile": "profile configuration is invalid.",
    "engine_exception": "failed unexpectedly.",
    "engine_failure": "failed.",
    "executable_missing": "is unavailable.",
    "execution_failed": "execution failed.",
    "invalid_output": "produced an invalid output artifact.",
    "invalid_package": "produced an invalid output package.",
    "invalid_profile": "profile configuration is invalid.",
    "missing_gcode": "output did not contain plate G-code.",
    "missing_output": "did not produce an output artifact.",
    "missing_stats": "output did not contain required estimates.",
    "probe_failed": "failed its runtime availability check.",
    "probe_timeout": "runtime availability check timed out.",
    "profile_cycle": "profile configuration is invalid.",
    "profile_missing": "required profile is unavailable.",
    "profile_root_missing": "profile configuration is unavailable.",
    "profile_write_failed": "could not prepare resolved profiles.",
    "timeout": "timed out.",
    "version_mismatch": "runtime version is unsupported.",
    "version_unrecognized": "runtime version could not be verified.",
    "workspace_error": "could not prepare its workspace.",
    "workspace_unavailable": "could not prepare its profile workspace.",
}
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestratedFailure:
    """Bounded engine failure details safe for public result metadata."""

    engine_key: str
    code: str
    message: str


@dataclass(frozen=True)
class OrchestratedResult:
    artifact: EngineArtifact | None
    fallback_used: bool
    primary_failure: OrchestratedFailure | None
    failures: tuple[OrchestratedFailure, ...]

    @property
    def success(self) -> bool:
        return self.artifact is not None


class SlicerOrchestrator:
    """Run configured slicer adapters in order under one strict fallback policy."""

    def __init__(
        self,
        engines: Mapping[str, SlicerEngine],
        engine_order: str | Sequence[str] = DEFAULT_ENGINE_ORDER,
    ) -> None:
        normalized_order = self._normalize_engine_order(engine_order)
        missing = [engine_key for engine_key in normalized_order if engine_key not in engines]
        if missing:
            raise ValueError(f"Invalid engine order: no adapter is configured for {missing[0]!r}.")

        self._engines = {engine_key: engines[engine_key] for engine_key in normalized_order}
        self.engine_order = normalized_order

    def slice(
        self,
        model_path: Path,
        workspace: Path,
        options: SliceOptions,
    ) -> OrchestratedResult:
        failures: list[OrchestratedFailure] = []

        for position, engine_key in enumerate(self.engine_order):
            adapter_options = replace(options, slicer_options=deepcopy(options.slicer_options))
            try:
                outcome = self._engines[engine_key].slice(model_path, workspace, adapter_options)
            except RequestValidationError:
                raise
            except Exception:
                _LOGGER.exception("Slicer adapter %s raised an unexpected exception.", engine_key)
                outcome = EngineFailure(
                    engine_key=engine_key,
                    code="engine_exception",
                    message="",
                    fallback_eligible=True,
                )
            fallback_used = position > 0

            if isinstance(outcome, EngineArtifact):
                artifact = self._enforce_artifact_policy(engine_key, outcome)
                return OrchestratedResult(
                    artifact=artifact,
                    fallback_used=fallback_used,
                    primary_failure=failures[0] if fallback_used else None,
                    failures=tuple(failures),
                )

            if not isinstance(outcome, EngineFailure):
                outcome = EngineFailure(
                    engine_key=engine_key,
                    code="engine_failure",
                    message="",
                    fallback_eligible=True,
                )

            failure = self._public_failure(engine_key, outcome)
            failures.append(failure)
            has_next_engine = position + 1 < len(self.engine_order)
            if not outcome.fallback_eligible or not has_next_engine:
                return OrchestratedResult(
                    artifact=None,
                    fallback_used=fallback_used,
                    primary_failure=failures[0] if fallback_used else None,
                    failures=tuple(failures),
                )

        raise RuntimeError("The validated slicer engine order was unexpectedly empty.")

    @staticmethod
    def _normalize_engine_order(engine_order: str | Sequence[str]) -> tuple[str, ...]:
        if isinstance(engine_order, str):
            values = engine_order.split(",")
        else:
            values = list(engine_order)

        normalized = tuple(str(value).strip().lower() for value in values)
        if normalized != DEFAULT_ENGINE_ORDER:
            raise ValueError("Invalid engine order: expected exactly 'bambu,prusa'.")
        return normalized

    @staticmethod
    def _public_failure(engine_key: str, failure: EngineFailure) -> OrchestratedFailure:
        code = failure.code if isinstance(failure.code, str) else "engine_failure"
        if code not in _PUBLIC_FAILURE_SUFFIXES:
            code = "engine_failure"
        engine_name = _ENGINE_NAMES[engine_key]
        message = f"{engine_name} {_PUBLIC_FAILURE_SUFFIXES[code]}"
        return OrchestratedFailure(
            engine_key=engine_key,
            code=code,
            message=message[:MAX_PUBLIC_FAILURE_MESSAGE_CHARS],
        )

    @staticmethod
    def _enforce_artifact_policy(engine_key: str, artifact: EngineArtifact) -> EngineArtifact:
        if engine_key != "prusa" or (artifact.estimate_only and not artifact.direct_print_eligible):
            return artifact
        return replace(
            artifact,
            direct_print_eligible=False,
            estimate_only=True,
        )
