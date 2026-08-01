from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.engines.base import (
    EngineArtifact,
    EngineFailure,
    RequestValidationError,
    SliceOptions,
)
from app.services.engines.orchestrator import DEFAULT_ENGINE_ORDER, SlicerOrchestrator


_EXPECTED_BAMBU_MESSAGES = {
    "executable_missing": "Bambu Studio is unavailable.",
    "timeout": "Bambu Studio timed out.",
    "execution_failed": "Bambu Studio execution failed.",
    "missing_output": "Bambu Studio did not produce an output artifact.",
    "invalid_output": "Bambu Studio produced an invalid output artifact.",
    "missing_stats": "Bambu Studio output did not contain required estimates.",
}


@dataclass
class _FakeEngine:
    engine_key: str
    result: EngineArtifact | EngineFailure | BaseException

    def __post_init__(self) -> None:
        self.calls: list[tuple[Path, Path, SliceOptions]] = []

    def slice(
        self,
        model_path: Path,
        workspace: Path,
        options: SliceOptions,
    ) -> EngineArtifact | EngineFailure:
        self.calls.append((model_path, workspace, options))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _options() -> SliceOptions:
    return SliceOptions.from_request(
        "bambu_a1",
        {"model_filename": "model.stl", "material": "PLA", "nozzle_diameter": "0.4"},
        preserve_orientation=True,
    )


def _artifact(tmp_path: Path, engine_key: str, *, claims_direct_print: bool = False) -> EngineArtifact:
    suffix = ".gcode.3mf" if engine_key == "bambu" else ".gcode"
    artifact_path = tmp_path / f"model{suffix}"
    artifact_path.write_bytes(b"artifact")
    return EngineArtifact(
        engine_key=engine_key,
        engine_name="Bambu Studio" if engine_key == "bambu" else "PrusaSlicer",
        engine_version="2.7.1.62" if engine_key == "bambu" else "2.8.1",
        artifact_path=artifact_path,
        artifact_filename=artifact_path.name,
        artifact_media_type="application/octet-stream",
        artifact_size=artifact_path.stat().st_size,
        artifact_sha256="0" * 64,
        filament_grams=Decimal("5.25"),
        print_minutes=Decimal("42"),
        layer_count=100,
        profile_ids={"machine": "A1"},
        direct_print_eligible=claims_direct_print,
        estimate_only=not claims_direct_print,
    )


def _failure(
    code: str,
    *,
    engine_key: str = "bambu",
    fallback_eligible: bool = True,
    message: str | None = None,
) -> EngineFailure:
    return EngineFailure(
        engine_key=engine_key,
        code=code,
        message=message or f"{engine_key} failed: {code}",
        fallback_eligible=fallback_eligible,
        diagnostics={"stderr": "private engine output must not escape"},
    )


def _orchestrator(bambu: _FakeEngine, prusa: _FakeEngine, engine_order=None) -> SlicerOrchestrator:
    kwargs = {} if engine_order is None else {"engine_order": engine_order}
    return SlicerOrchestrator({"bambu": bambu, "prusa": prusa}, **kwargs)


def test_bambu_success_returns_immediately_without_calling_prusa(tmp_path: Path):
    bambu = _FakeEngine("bambu", _artifact(tmp_path, "bambu", claims_direct_print=True))
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.success is True
    assert result.artifact is bambu.result
    assert result.fallback_used is False
    assert result.primary_failure is None
    assert result.failures == ()
    assert len(bambu.calls) == 1
    assert prusa.calls == []


@pytest.mark.parametrize(
    "code",
    [
        "executable_missing",
        "timeout",
        "execution_failed",
        "missing_output",
        "invalid_output",
        "missing_stats",
    ],
)
def test_fallback_eligible_bambu_failures_call_prusa_once(tmp_path: Path, code: str):
    bambu_failure = _failure(code)
    bambu = _FakeEngine("bambu", bambu_failure)
    prusa_artifact = _artifact(tmp_path, "prusa")
    prusa = _FakeEngine("prusa", prusa_artifact)

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.success is True
    assert result.artifact is prusa_artifact
    assert result.fallback_used is True
    assert result.primary_failure is not None
    assert result.primary_failure.engine_key == "bambu"
    assert result.primary_failure.code == code
    assert result.primary_failure.message == _EXPECTED_BAMBU_MESSAGES[code]
    assert len(prusa.calls) == 1


def test_primary_failure_metadata_is_bounded_and_excludes_engine_diagnostics(tmp_path: Path):
    bambu = _FakeEngine("bambu", _failure("execution_failed", message="x" * 2_000))
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.primary_failure is not None
    assert len(result.primary_failure.message) <= 512
    assert result.primary_failure.message == "Bambu Studio execution failed."
    assert not hasattr(result.primary_failure, "diagnostics")
    assert "private engine output" not in repr(result.primary_failure)


@pytest.mark.parametrize(
    ("adapter_code", "expected_code"),
    [
        ("timeout", "timeout"),
        ("../../private/workspace/" + "x" * 2_000, "engine_failure"),
    ],
)
def test_primary_failure_metadata_uses_configured_provenance_and_safe_public_values(
    tmp_path: Path,
    adapter_code: str,
    expected_code: str,
):
    malicious_failure = EngineFailure(
        engine_key="prusa",
        code=adapter_code,
        message=f"secret failed at {tmp_path}/private/workspace\x00" + "y" * 2_000,
        fallback_eligible=True,
        diagnostics={"stderr": f"token and path: {tmp_path}/private/workspace"},
    )
    bambu = _FakeEngine("bambu", malicious_failure)
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.primary_failure is not None
    assert result.primary_failure.engine_key == "bambu"
    assert result.primary_failure.code == expected_code
    assert result.primary_failure.message in {
        "Bambu Studio timed out.",
        "Bambu Studio failed.",
    }
    public_result = repr(result.primary_failure)
    assert str(tmp_path) not in public_result
    assert "private/workspace" not in public_result
    assert "token" not in public_result
    assert "secret" not in public_result


def test_secondary_failure_metadata_uses_prusa_provenance_not_adapter_claim(tmp_path: Path):
    bambu = _FakeEngine("bambu", _failure("timeout"))
    malicious_prusa = EngineFailure(
        engine_key="bambu",
        code="unknown/../../code",
        message=f"Prusa leaked {tmp_path}/private/output.gcode",
        fallback_eligible=True,
        diagnostics={"stderr": "private diagnostics"},
    )
    prusa = _FakeEngine("prusa", malicious_prusa)

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.success is False
    assert result.failures[1].engine_key == "prusa"
    assert result.failures[1].code == "engine_failure"
    assert result.failures[1].message == "PrusaSlicer failed."
    assert str(tmp_path) not in repr(result)
    assert "private diagnostics" not in repr(result)


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("unsupported_printer", "Unsupported printer"),
        ("unsupported_nozzle", "Unsupported nozzle"),
        ("unsupported_material", "Unsupported material"),
        ("unsupported_profile", "Unsupported profile"),
        ("unsupported_model_suffix", "Unsupported suffix"),
        ("malformed_request", "Malformed request"),
    ],
)
def test_terminal_request_validation_never_calls_prusa(tmp_path: Path, code: str, message: str):
    request_error = RequestValidationError(code, message)
    bambu = _FakeEngine("bambu", request_error)
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    with pytest.raises(RequestValidationError) as error:
        _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert error.value is request_error
    assert len(bambu.calls) == 1
    assert prusa.calls == []


def test_unexpected_bambu_exception_becomes_fallback_eligible_public_failure(tmp_path: Path):
    bambu = _FakeEngine("bambu", RuntimeError(f"crash in {tmp_path}/private/workspace"))
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.success is True
    assert result.fallback_used is True
    assert result.primary_failure is not None
    assert result.primary_failure.engine_key == "bambu"
    assert result.primary_failure.code == "engine_exception"
    assert result.primary_failure.message == "Bambu Studio failed unexpectedly."
    assert str(tmp_path) not in repr(result.primary_failure)
    assert len(prusa.calls) == 1


def test_unexpected_prusa_exception_returns_both_stable_failure_codes(tmp_path: Path):
    bambu = _FakeEngine("bambu", _failure("timeout"))
    prusa = _FakeEngine("prusa", RuntimeError(f"crash in {tmp_path}/private/workspace"))

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.success is False
    assert [(failure.engine_key, failure.code) for failure in result.failures] == [
        ("bambu", "timeout"),
        ("prusa", "engine_exception"),
    ]
    assert result.failures[1].message == "PrusaSlicer failed unexpectedly."
    assert str(tmp_path) not in repr(result)


def test_base_exceptions_are_not_caught_or_converted(tmp_path: Path):
    shutdown = SystemExit(17)
    bambu = _FakeEngine("bambu", shutdown)
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    with pytest.raises(SystemExit) as error:
        _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert error.value is shutdown
    assert prusa.calls == []


def test_non_fallback_engine_failure_is_terminal_and_never_calls_prusa(tmp_path: Path):
    terminal_failure = _failure("invalid_request", fallback_eligible=False)
    bambu = _FakeEngine("bambu", terminal_failure)
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.success is False
    assert result.artifact is None
    assert [failure.code for failure in result.failures] == ["engine_failure"]
    assert result.fallback_used is False
    assert prusa.calls == []


def test_dual_engine_failure_returns_both_stable_failure_codes(tmp_path: Path):
    bambu = _FakeEngine("bambu", _failure("timeout"))
    prusa = _FakeEngine("prusa", _failure("missing_stats", engine_key="prusa"))

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.success is False
    assert result.artifact is None
    assert result.fallback_used is True
    assert [(failure.engine_key, failure.code) for failure in result.failures] == [
        ("bambu", "timeout"),
        ("prusa", "missing_stats"),
    ]
    assert result.primary_failure == result.failures[0]


def test_fallback_artifact_is_forced_estimate_only_even_when_adapter_lies(tmp_path: Path):
    bambu = _FakeEngine("bambu", _failure("execution_failed"))
    lying_artifact = _artifact(tmp_path, "prusa", claims_direct_print=True)
    prusa = _FakeEngine("prusa", lying_artifact)

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, _options())

    assert result.artifact is not None
    assert result.artifact is not lying_artifact
    assert result.artifact.engine_key == "prusa"
    assert result.artifact.estimate_only is True
    assert result.artifact.direct_print_eligible is False


def test_each_adapter_receives_an_isolated_copy_of_mutable_slicer_options(tmp_path: Path):
    class _MutatingBambu(_FakeEngine):
        def slice(self, model_path, workspace, options):
            self.calls.append((model_path, workspace, options))
            options.slicer_options["new_key"] = "mutated"
            options.slicer_options["nested"]["value"] = "mutated"
            return self.result

    options = _options()
    options.slicer_options["nested"] = {"value": "original"}
    bambu = _MutatingBambu("bambu", _failure("timeout"))
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    result = _orchestrator(bambu, prusa).slice(tmp_path / "model.stl", tmp_path, options)

    assert result.success is True
    assert bambu.calls[0][2] is not options
    assert prusa.calls[0][2] is not options
    assert bambu.calls[0][2] is not prusa.calls[0][2]
    assert prusa.calls[0][2].slicer_options["nested"] == {"value": "original"}
    assert "new_key" not in prusa.calls[0][2].slicer_options
    assert options.slicer_options["nested"] == {"value": "original"}
    assert "new_key" not in options.slicer_options


def test_default_engine_order_is_exactly_bambu_then_prusa(tmp_path: Path):
    bambu = _FakeEngine("bambu", _artifact(tmp_path, "bambu"))
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    orchestrator = _orchestrator(bambu, prusa)

    assert DEFAULT_ENGINE_ORDER == ("bambu", "prusa")
    assert orchestrator.engine_order == DEFAULT_ENGINE_ORDER


@pytest.mark.parametrize(
    "engine_order",
    [
        "bambu,orca",
        ("unknown",),
        "",
        "bambu",
        ("bambu",),
        "bambu,bambu",
        "prusa,bambu",
        "bambu,prusa,bambu",
    ],
)
def test_unknown_or_invalid_engine_configuration_is_rejected_at_construction(
    tmp_path: Path,
    engine_order,
):
    bambu = _FakeEngine("bambu", _artifact(tmp_path, "bambu"))
    prusa = _FakeEngine("prusa", _artifact(tmp_path, "prusa"))

    with pytest.raises(ValueError, match="engine order"):
        _orchestrator(bambu, prusa, engine_order=engine_order)


def test_missing_required_adapter_is_rejected_at_construction(tmp_path: Path):
    bambu = _FakeEngine("bambu", _artifact(tmp_path, "bambu"))

    with pytest.raises(ValueError, match="engine order"):
        SlicerOrchestrator({"bambu": bambu})
