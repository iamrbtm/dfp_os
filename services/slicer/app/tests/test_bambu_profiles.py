from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.services.engines.bambu_profiles import BambuProfileError, BambuProfileResolver


MATRIX = {
    "bambu_a1": (
        "Bambu Lab A1 0.4 nozzle",
        "0.20mm Standard @BBL A1",
        "Generic {material} @BBL A1",
    ),
    "bambu_p1p": (
        "Bambu Lab P1P 0.4 nozzle",
        "0.20mm Standard @BBL P1P",
        "Generic {material} @BBL P1P",
    ),
    "bambu_x1c": (
        "Bambu Lab X1 Carbon 0.4 nozzle",
        "0.20mm Standard @BBL X1C",
        "Generic {material}",
    ),
}
MATERIALS = ("PLA", "PETG", "ABS", "ASA", "TPU")


def _write_profile(profile_root: Path, relative_path: str, **profile: object) -> None:
    path = profile_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile), encoding="utf-8")


@pytest.fixture
def profile_root(tmp_path: Path) -> Path:
    root = tmp_path / "BBL"
    _write_profile(
        root,
        "ancestors/root.json",
        name="machine-root",
        oldest="root",
        precedence="root",
        nested={"level": {"value": "original"}},
    )
    _write_profile(
        root,
        "ancestors/parent-with-an-unrelated-filename.json",
        name="machine-parent",
        inherits="machine-root",
        parent_only="parent",
        precedence="parent",
    )
    _write_profile(root, "fragments/first.json", name="machine-include-one", include_order="first")
    _write_profile(
        root,
        "fragments/second.json",
        name="machine-include-two",
        include_order="second",
        include_only="fragment",
        precedence="include",
    )

    for printer, (machine, process, filament_pattern) in MATRIX.items():
        machine_values: dict[str, object] = {"name": machine, "printer_key": printer}
        if printer == "bambu_a1":
            machine_values.update(
                inherits="machine-parent",
                include=["machine-include-one", "machine-include-two"],
                selected_only="machine",
                precedence="selected",
            )
        _write_profile(root, f"machines/{printer}-selected.json", **machine_values)
        _write_profile(root, f"processes/{printer}.json", name=process, process_key=printer)
        for material in MATERIALS:
            name = filament_pattern.format(material=material)
            _write_profile(
                root,
                f"filaments/{printer}/{material.lower()}.json",
                name=name,
                material=material,
            )

    # Real BBL resources contain auxiliary JSON documents without a profile name.
    _write_profile(root, "metadata/lookup.json", description="not a selectable profile")
    return root


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_resolve_indexes_json_name_and_flattens_inheritance_and_includes(profile_root: Path, tmp_path: Path):
    workspace = tmp_path / "request-workspace"

    resolved = BambuProfileResolver(profile_root).resolve("bambu_a1", "PLA", workspace)

    machine = _read(resolved.machine_path)
    assert machine["oldest"] == "root"
    assert machine["parent_only"] == "parent"
    assert machine["include_only"] == "fragment"
    assert machine["include_order"] == "second"
    assert machine["selected_only"] == "machine"
    assert machine["precedence"] == "selected"
    assert machine["name"] == "Bambu Lab A1 0.4 nozzle"
    assert "inherits" not in machine
    assert "include" not in machine


@pytest.mark.parametrize("printer", MATRIX)
@pytest.mark.parametrize("material", MATERIALS)
def test_resolve_uses_the_exact_allowlisted_official_matrix(
    profile_root: Path, tmp_path: Path, printer: str, material: str
):
    machine, process, filament_pattern = MATRIX[printer]

    resolved = BambuProfileResolver(profile_root).resolve(printer, material, tmp_path / f"{printer}-{material}")

    assert resolved.profile_ids == {
        "machine": machine,
        "process": process,
        "filament": filament_pattern.format(material=material),
    }
    assert _read(resolved.machine_path)["name"] == machine
    assert _read(resolved.process_path)["name"] == process
    assert _read(resolved.filament_path)["name"] == filament_pattern.format(material=material)


def test_validate_required_matrix_flattens_every_allowlisted_profile(profile_root: Path):
    resolver = BambuProfileResolver(profile_root)

    resolver.validate_required_matrix()

    expected_names = {
        name.format(material=material)
        for machine, process, filament in MATRIX.values()
        for name in (machine, process, filament)
        for material in MATERIALS
    }
    assert expected_names <= set(resolver._flattened)


def test_validate_required_matrix_reports_a_stable_missing_profile(profile_root: Path):
    (profile_root / "filaments/bambu_x1c/asa.json").unlink()
    resolver = BambuProfileResolver(profile_root)

    with pytest.raises(BambuProfileError) as error:
        resolver.validate_required_matrix()

    assert error.value.code == "profile_missing"
    assert str(profile_root) not in error.value.message


def test_resolve_writes_fresh_flattened_files_in_each_request_workspace(profile_root: Path, tmp_path: Path):
    resolver = BambuProfileResolver(profile_root)
    first = resolver.resolve("bambu_a1", "PLA", tmp_path / "one")
    second = resolver.resolve("bambu_a1", "PLA", tmp_path / "two")

    assert (first.machine_path.name, first.process_path.name, first.filament_path.name) == (
        "machine.json",
        "process.json",
        "filament.json",
    )
    assert first.machine_path.parent == tmp_path / "one"
    assert second.machine_path.parent == tmp_path / "two"
    assert first.machine_path.read_bytes() == second.machine_path.read_bytes()


def test_cached_source_and_flattened_profiles_cannot_be_mutated_across_requests(profile_root: Path, tmp_path: Path):
    resolver = BambuProfileResolver(profile_root)

    with pytest.raises(TypeError):
        resolver._profiles["machine-root"]["oldest"] = "corrupted"

    first = resolver._flatten("Bambu Lab A1 0.4 nozzle")
    first["nested"]["level"]["value"] = "corrupted"
    second = resolver._flatten("Bambu Lab A1 0.4 nozzle")
    resolved = resolver.resolve("bambu_a1", "PLA", tmp_path / "workspace")

    assert second["nested"]["level"]["value"] == "original"
    assert _read(resolved.machine_path)["nested"]["level"]["value"] == "original"


def test_concurrent_resolves_use_isolated_request_files(profile_root: Path, tmp_path: Path):
    resolver = BambuProfileResolver(profile_root)

    def resolve(index: int) -> tuple[Path, bytes]:
        result = resolver.resolve("bambu_a1", "PLA", tmp_path / f"request-{index}")
        return result.machine_path, result.machine_path.read_bytes()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(resolve, range(24)))

    assert len({path.parent for path, _content in results}) == 24
    assert len({content for _path, content in results}) == 1
    assert _read(results[0][0])["nested"]["level"]["value"] == "original"


@pytest.mark.parametrize(
    ("printer", "material", "expected_code"),
    [
        ("../../etc/passwd", "PLA", "unsupported_printer"),
        ("bambu_a1", "../../../secret", "unsupported_material"),
    ],
)
def test_resolve_rejects_request_values_outside_the_allowlisted_matrix(
    profile_root: Path, tmp_path: Path, printer: str, material: str, expected_code: str
):
    with pytest.raises(BambuProfileError) as error:
        BambuProfileResolver(profile_root).resolve(printer, material, tmp_path / "workspace")

    assert error.value.code == expected_code


@pytest.mark.parametrize(
    ("broken_profile", "expected_code"),
    [
        ({"inherits": "missing-parent"}, "profile_missing"),
        ({"inherits": "Bambu Lab A1 0.4 nozzle"}, "profile_cycle"),
    ],
)
def test_resolve_reports_stable_errors_for_missing_parent_or_cycle(
    profile_root: Path, tmp_path: Path, broken_profile: dict[str, object], expected_code: str
):
    selected = profile_root / "machines/bambu_a1-selected.json"
    values = json.loads(selected.read_text(encoding="utf-8"))
    values.update(broken_profile)
    selected.write_text(json.dumps(values), encoding="utf-8")

    with pytest.raises(BambuProfileError) as error:
        BambuProfileResolver(profile_root).resolve("bambu_a1", "PLA", tmp_path / "workspace")

    assert error.value.code == expected_code


def test_resolver_rejects_duplicate_profile_names_instead_of_choosing_by_scan_order(profile_root: Path, tmp_path: Path):
    _write_profile(profile_root, "duplicates/duplicate.json", name="Generic PLA @BBL A1")

    with pytest.raises(BambuProfileError) as error:
        BambuProfileResolver(profile_root).resolve("bambu_a1", "PLA", tmp_path / "workspace")

    assert error.value.code == "duplicate_profile"


def test_resolve_wraps_an_unusable_workspace_with_a_stable_error(profile_root: Path, tmp_path: Path):
    workspace = tmp_path / "not-a-directory"
    workspace.write_text("occupied", encoding="utf-8")

    with pytest.raises(BambuProfileError) as error:
        BambuProfileResolver(profile_root).resolve("bambu_a1", "PLA", workspace)

    assert error.value.code == "workspace_unavailable"


def test_resolve_wraps_profile_write_failures_with_a_stable_error(profile_root: Path, tmp_path: Path, monkeypatch):
    def fail_write(*_args, **_kwargs):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(Path, "write_text", fail_write)

    with pytest.raises(BambuProfileError) as error:
        BambuProfileResolver(profile_root).resolve("bambu_a1", "PLA", tmp_path / "workspace")

    assert error.value.code == "profile_write_failed"
