from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Sequence

from app.services.engines.base import EngineArtifact, EngineFailure, SliceOptions, SlicerEngine


DEFAULT_ENGINE_ORDER = ("bambu", "prusa")
MAX_PUBLIC_FAILURE_MESSAGE_CHARS = 512


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
            outcome = self._engines[engine_key].slice(model_path, workspace, options)
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
                raise TypeError(f"Slicer adapter {engine_key!r} returned an invalid result.")

            failure = self._public_failure(outcome)
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
        if not normalized or any(not value for value in normalized):
            raise ValueError("Invalid engine order: at least one engine key is required.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Invalid engine order: duplicate engine keys are not allowed.")

        unknown = [engine_key for engine_key in normalized if engine_key not in DEFAULT_ENGINE_ORDER]
        if unknown:
            raise ValueError(f"Invalid engine order: unknown engine key {unknown[0]!r}.")
        if normalized[0] != "bambu":
            raise ValueError("Invalid engine order: Bambu Studio must be the primary engine.")
        return normalized

    @staticmethod
    def _public_failure(failure: EngineFailure) -> OrchestratedFailure:
        message = str(failure.message).replace("\x00", "").strip()
        return OrchestratedFailure(
            engine_key=failure.engine_key,
            code=failure.code,
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
