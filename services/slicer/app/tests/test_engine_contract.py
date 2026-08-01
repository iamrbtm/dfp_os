from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.engines.base import EngineFailure, RequestValidationError, SliceOptions


def test_slice_options_normalizes_supported_profile_and_accepts_supported_request_values():
    options = SliceOptions.from_request(
        "bambu_a1.ini",
        {
            "model_filename": "rainbow-dragon.stl",
            "nozzle_diameter": "0.4",
            "material": "PLA",
        },
        preserve_orientation=True,
    )

    assert options.printer == "bambu_a1"
    assert options.nozzle_diameter == Decimal("0.4")
    assert options.material == "PLA"
    assert options.model_suffix == ".stl"
    assert options.preserve_orientation is True


@pytest.mark.parametrize("profile_name", ["bambu_a1", "bambu_p1p", "bambu_x1c"])
def test_slice_options_accepts_each_supported_printer(profile_name: str):
    options = SliceOptions.from_request(profile_name, {"model_filename": "model.3mf"}, False)

    assert options.printer == profile_name


def test_slice_options_rejects_unsupported_nozzle_as_terminal_request_failure():
    with pytest.raises(RequestValidationError) as error:
        SliceOptions.from_request(
            "bambu_a1",
            {"model_filename": "model.stl", "nozzle_diameter": "0.6"},
            False,
        )

    assert error.value.code == "unsupported_nozzle"
    assert error.value.fallback_eligible is False


@pytest.mark.parametrize("material", ["PLA", "PETG", "ABS", "ASA", "TPU"])
def test_slice_options_accepts_each_supported_material(material: str):
    options = SliceOptions.from_request(
        "bambu_a1",
        {"model_filename": "model.obj", "material": material},
        False,
    )

    assert options.material == material


def test_slice_options_rejects_unsupported_model_suffix_before_engine_selection():
    with pytest.raises(RequestValidationError) as error:
        SliceOptions.from_request("bambu_a1", {"model_filename": "model.exe"}, False)

    assert error.value.code == "unsupported_model_suffix"
    assert error.value.fallback_eligible is False


def test_engine_failure_marks_engine_errors_as_fallback_eligible_and_request_errors_as_terminal():
    engine_failure = EngineFailure(
        engine_key="bambu",
        code="engine_unavailable",
        message="Bambu Studio is unavailable.",
        fallback_eligible=True,
    )
    request_failure = RequestValidationError("unsupported_material", "Material is unsupported.")

    assert engine_failure.fallback_eligible is True
    assert request_failure.fallback_eligible is False
