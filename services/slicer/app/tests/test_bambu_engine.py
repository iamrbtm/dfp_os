from __future__ import annotations

import hashlib
import subprocess
import zipfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.engines.bambu import BambuEngine
from app.services.engines.bambu_profiles import ResolvedBambuProfiles
from app.services.engines.base import EngineFailure, RequestValidationError, SliceOptions
from app.services.engines.stats import _parse_gcode_stats


FIXTURES = Path(__file__).parent / "fixtures"
PACKAGE_FIXTURE = FIXTURES / "minimal_gcode_3mf"
PINNED_HELP = b"BambuStudio-02.07.01.62\n"
VALID_GCODE = (PACKAGE_FIXTURE / "Metadata/plate_1.gcode").read_text(encoding="utf-8")


class _Proc:
    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Resolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Path]] = []

    def resolve(self, printer: str, material: str, workspace: Path) -> ResolvedBambuProfiles:
        workspace = Path(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        self.calls.append((printer, material, workspace))
        paths = [workspace / name for name in ("machine.json", "process.json", "filament.json")]
        for path in paths:
            path.write_text("{}\n", encoding="utf-8")
        return ResolvedBambuProfiles(
            machine_path=paths[0],
            process_path=paths[1],
            filament_path=paths[2],
            profile_ids={"machine": "A1", "process": "Standard", "filament": "Generic PLA"},
        )

    def validate_required_matrix(self) -> None:
        return None


def _options(filename: str = "rainbow dragon.stl", **overrides: object) -> SliceOptions:
    values: dict[str, object] = {
        "model_filename": filename,
        "nozzle_diameter": "0.4",
        "material": "PLA",
        "layer_height": "0.16",
        "perimeters": 3,
        "top_solid_layers": 4,
        "bottom_solid_layers": 5,
        "infill_percent": "0.2",
        "infill_pattern": "gyroid",
        "supports": "build_plate",
        "brim_width": "4",
    }
    values.update(overrides)
    return SliceOptions.from_request("bambu_a1", values, preserve_orientation=False)


def _model(tmp_path: Path, filename: str = "rainbow dragon.stl") -> Path:
    path = tmp_path / filename
    path.write_bytes((FIXTURES / "cube.stl").read_bytes())
    return path


def _artifact_path(command: list[str]) -> Path:
    return Path(command[command.index("--export-3mf") + 1])


def _write_artifact(
    command: list[str],
    *,
    plates: dict[str, str] | None = None,
    include_structure: bool = True,
    compression: int = zipfile.ZIP_DEFLATED,
    structure_overrides: dict[str, bytes] | None = None,
) -> Path:
    output = _artifact_path(command)
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        if include_structure:
            for path in sorted(PACKAGE_FIXTURE.rglob("*")):
                relative = path.relative_to(PACKAGE_FIXTURE).as_posix()
                if path.is_file() and not relative.startswith("Metadata/plate_"):
                    archive.writestr(relative, (structure_overrides or {}).get(relative, path.read_bytes()))
        for member, gcode in (plates if plates is not None else {"Metadata/plate_1.gcode": VALID_GCODE}).items():
            archive.writestr(member, gcode)
    return output


def _versioned_runner(slice_runner):
    def run(command, **kwargs):
        if "--help" in command:
            return _Proc(stdout=PINNED_HELP)
        return slice_runner(command, **kwargs)

    return run


def test_probe_uses_apprun_help_without_a_shell_and_normalizes_the_pinned_version(monkeypatch):
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return _Proc(stdout=b"BambuStudio-02.07.01.62\n")

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", fake_run)

    probe = BambuEngine("/opt/bambu-studio/AppRun", _Resolver()).probe()

    assert probe.available is True
    assert probe.engine_version == "2.7.1.62"
    assert calls[0][0] == ["/opt/bambu-studio/AppRun", "--help"]
    assert calls[0][1]["shell"] is False


def test_probe_reports_required_profile_matrix_failure_with_stable_code(monkeypatch):
    from app.services.engines.bambu_profiles import BambuProfileError

    class BrokenResolver(_Resolver):
        def validate_required_matrix(self) -> None:
            raise BambuProfileError("profile_missing", "private /profile/root")

    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        lambda _command, **_kwargs: _Proc(stdout=PINNED_HELP),
    )

    probe = BambuEngine("/opt/bambu-studio/AppRun", BrokenResolver()).probe()

    assert probe.available is False
    assert probe.diagnostics == {"code": "profile_missing"}
    assert "private" not in str(probe.diagnostics)


def test_cached_bambu_probe_does_not_reduce_later_slice_budget(tmp_path, monkeypatch):
    timeouts: list[float] = []

    def fake_run(command, **kwargs):
        timeouts.append(kwargs["timeout"])
        if "--help" in command:
            return _Proc(stdout=PINNED_HELP)
        _write_artifact(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", fake_run)
    engine = BambuEngine("AppRun", _Resolver(), timeout=10, probe_timeout=3)

    assert engine.probe().available is True
    artifact = engine.slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert not isinstance(artifact, EngineFailure)
    assert timeouts == [3, 10]


def test_slice_builds_safe_argument_array_and_returns_valid_native_artifact(tmp_path, monkeypatch):
    resolver = _Resolver()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if "--help" in command:
            return _Proc(stdout=PINNED_HELP)
        _write_artifact(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", fake_run)
    model_path = _model(tmp_path)
    workspace = tmp_path / "request-workspace"

    artifact = BambuEngine("/opt/bambu-studio/AppRun", resolver).slice(model_path, workspace, _options())

    assert not isinstance(artifact, EngineFailure)
    assert calls[0][0] == ["/opt/bambu-studio/AppRun", "--help"]
    command, kwargs = calls[1]
    assert isinstance(command, list)
    assert kwargs["shell"] is False
    assert command[0] == "/opt/bambu-studio/AppRun"
    settings = command[command.index("--load-settings") + 1].split(";")
    assert [Path(value).name for value in settings] == ["machine.json", "process.json"]
    assert Path(command[command.index("--load-filaments") + 1]).name == "filament.json"
    assert command[command.index("--arrange") + 1] == "1"
    assert command[command.index("--slice") + 1] == "0"
    assert "--orient" in command
    for expected in (
        "--layer-height=0.16",
        "--wall-loops=3",
        "--top-shell-layers=4",
        "--bottom-shell-layers=5",
        "--sparse-infill-density=20%",
        "--sparse-infill-pattern=gyroid",
        "--enable-support=1",
        "--support-on-build-plate-only=1",
        "--brim-width=4",
    ):
        assert expected in command
    assert artifact.artifact_filename == "rainbow-dragon.gcode.3mf"
    assert artifact.artifact_media_type == "application/vnd.bambulab.gcode-3mf"
    assert artifact.artifact_size == artifact.artifact_path.stat().st_size
    assert artifact.artifact_sha256 == hashlib.sha256(artifact.artifact_path.read_bytes()).hexdigest()
    assert artifact.filament_grams == Decimal("6.25")
    assert artifact.print_minutes == Decimal("62.0")
    assert artifact.layer_count == 123
    assert artifact.profile_ids == {"machine": "A1", "process": "Standard", "filament": "Generic PLA"}
    assert artifact.direct_print_eligible is True
    assert artifact.estimate_only is False
    assert artifact.engine_version == "2.7.1.62"
    assert resolver.calls == [("bambu_a1", "PLA", workspace)]


def test_slice_preserves_uploaded_orientation_when_requested(tmp_path, monkeypatch):
    def fake_run(command, **_kwargs):
        _write_artifact(command)
        assert "--orient" not in command
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))
    options = replace(_options(), preserve_orientation=True)

    artifact = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", options)

    assert not isinstance(artifact, EngineFailure)


@pytest.mark.parametrize(
    ("supports", "expected", "unexpected"),
    [
        ("none", {"--enable-support=0"}, {"--support-on-build-plate-only=0", "--support-on-build-plate-only=1"}),
        ("everywhere", {"--enable-support=1", "--support-on-build-plate-only=0"}, set()),
        ("build_plate", {"--enable-support=1", "--support-on-build-plate-only=1"}, set()),
    ],
)
def test_slice_maps_each_support_mode(tmp_path, monkeypatch, supports, expected, unexpected):
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        _write_artifact(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    artifact = BambuEngine("AppRun", _Resolver()).slice(
        _model(tmp_path), tmp_path / "workspace", _options(supports=supports)
    )

    assert not isinstance(artifact, EngineFailure)
    assert expected <= set(commands[0])
    assert set(commands[0]).isdisjoint(unexpected)


@pytest.mark.parametrize(
    ("runner", "expected_code"),
    [
        (lambda _command, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()), "executable_missing"),
        (
            lambda _command, **_kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("AppRun", 37)),
            "timeout",
        ),
        (lambda _command, **_kwargs: (_ for _ in ()).throw(OSError("crash in /private/workspace")), "execution_failed"),
        (
            lambda _command, **_kwargs: _Proc(returncode=9, stderr=b"/private/workspace\n" + b"x" * 1024),
            "execution_failed",
        ),
    ],
)
def test_slice_classifies_runtime_failures_with_bounded_path_free_diagnostics(
    tmp_path, monkeypatch, runner, expected_code
):
    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(runner))

    failure = BambuEngine("AppRun", _Resolver(), timeout=37).slice(
        _model(tmp_path), tmp_path / "private-workspace", _options()
    )

    assert isinstance(failure, EngineFailure)
    assert failure.code == expected_code
    assert failure.fallback_eligible is True
    public_text = f"{failure.message} {failure.diagnostics}"
    assert len(str(failure.diagnostics.get("stderr", ""))) <= 512
    assert str(tmp_path) not in public_text
    assert "/private/workspace" not in public_text


@pytest.mark.parametrize(
    ("writer", "expected_code"),
    [
        (lambda _command: None, "missing_output"),
        (lambda command: _artifact_path(command).write_bytes(b"not a zip"), "invalid_output"),
        (lambda command: _write_artifact(command, plates={}), "missing_gcode"),
        (
            lambda command: _write_artifact(
                command,
                plates={"Metadata/plate_1.gcode": "; total filament weight [g] : 6.25\n"},
            ),
            "missing_stats",
        ),
    ],
)
def test_slice_rejects_missing_or_invalid_native_artifacts(tmp_path, monkeypatch, writer, expected_code):
    def fake_run(command, **_kwargs):
        writer(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == expected_code
    assert failure.fallback_eligible is True


def test_slice_removes_a_stale_artifact_before_running(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    stale = workspace / "rainbow-dragon.gcode.3mf"
    _write_artifact(["--export-3mf", str(stale)])
    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        _versioned_runner(lambda _command, **_kwargs: _Proc()),
    )

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), workspace, _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "missing_output"
    assert not stale.exists()


@pytest.mark.parametrize(
    ("changed", "expected_code"),
    [
        ({"printer": "../../other"}, "unsupported_printer"),
        ({"nozzle_diameter": Decimal("0.6")}, "unsupported_nozzle"),
        ({"material": "NYLON"}, "unsupported_material"),
        ({"model_suffix": ".exe"}, "unsupported_model_suffix"),
    ],
)
def test_slice_keeps_forged_request_values_terminal(tmp_path, monkeypatch, changed, expected_code):
    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("terminal input must not execute Bambu Studio"),
    )
    options = replace(_options(), **changed)

    with pytest.raises(RequestValidationError) as error:
        BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", options)

    assert error.value.code == expected_code
    assert error.value.fallback_eligible is False


def test_slice_rejects_an_unsafe_actual_model_extension_even_if_options_are_forged(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("unsafe input must not execute Bambu Studio"),
    )
    unsafe_model = _model(tmp_path, "payload.exe")

    with pytest.raises(RequestValidationError) as error:
        BambuEngine("AppRun", _Resolver()).slice(unsafe_model, tmp_path / "workspace", _options())

    assert error.value.code == "unsupported_model_suffix"


@pytest.mark.parametrize(
    ("filename", "embedded"),
    [("model.stl", True), ("model.obj", True), ("model.3mf", False)],
)
def test_slice_rejects_multicolor_without_an_embedded_3mf_recipe(tmp_path, monkeypatch, filename, embedded):
    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("unsupported multicolor must not execute Bambu Studio"),
    )
    options = _options(filename, multicolor=True, use_embedded_settings=embedded)

    with pytest.raises(RequestValidationError) as error:
        BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path, filename), tmp_path / "workspace", options)

    assert error.value.code == "unsupported_multicolor"
    assert error.value.fallback_eligible is False


def test_slice_allows_multicolor_only_for_3mf_with_embedded_settings_without_color_assignment(tmp_path, monkeypatch):
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        _write_artifact(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))
    options = _options("model.3mf", multicolor=True, use_embedded_settings=True)

    artifact = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path, "model.3mf"), tmp_path / "workspace", options)

    assert not isinstance(artifact, EngineFailure)
    assert not any(argument.startswith("--") and "color" in argument.lower() for argument in commands[0])


@pytest.mark.parametrize(
    "gcode",
    [
        ("; total filament weight [g] : 8.40\n; total estimated time: 42m 15s\n; total layer number: 87\n"),
        ("; total filament weight [g] = 8.40\n; total estimated time = 42m 15s\n; total layer number = 87\n"),
    ],
)
def test_shared_stats_parser_accepts_native_bambu_comment_variants_without_breaking_prusa(tmp_path, gcode):
    path = tmp_path / "native.gcode"
    path.write_text(gcode, encoding="utf-8")

    stats = _parse_gcode_stats(path)

    assert stats is not None
    assert stats["filament_grams"] == Decimal("8.40")
    assert stats["print_minutes"] == Decimal("42.25")
    assert stats["layer_count"] == 87


def test_slice_aggregates_every_plate_in_deterministic_numeric_order(tmp_path, monkeypatch):
    def fake_run(command, **_kwargs):
        _write_artifact(
            command,
            plates={
                "Metadata/plate_10.gcode": (
                    "; total filament weight [g] : 1.25\n; total estimated time: 10m\n; total layer number: 10\n"
                ),
                "Metadata/plate_2.gcode": (
                    "; total filament weight [g] : 2.50\n; total estimated time: 20m 30s\n; total layer number: 20\n"
                ),
                "Metadata/plate_1.gcode": VALID_GCODE,
            },
        )
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    artifact = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert not isinstance(artifact, EngineFailure)
    assert artifact.filament_grams == Decimal("10.00")
    assert artifact.print_minutes == Decimal("92.5")
    assert artifact.layer_count == 153
    assert artifact.diagnostics["stats"]["plate_members"] == [
        "Metadata/plate_1.gcode",
        "Metadata/plate_2.gcode",
        "Metadata/plate_10.gcode",
    ]


def test_slice_requires_a_minimal_opc_3mf_package_before_direct_print_eligibility(tmp_path, monkeypatch):
    def fake_run(command, **_kwargs):
        _write_artifact(command, include_structure=False)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "invalid_package"
    assert failure.fallback_eligible is True


def test_slice_rejects_invalid_required_package_xml(tmp_path, monkeypatch):
    def fake_run(command, **_kwargs):
        _write_artifact(command, structure_overrides={"3D/3dmodel.model": b"not xml"})
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "invalid_package"


@pytest.mark.parametrize(
    ("part", "payload"),
    [
        ("[Content_Types].xml", b"<junk/>"),
        ("_rels/.rels", b"<junk/>"),
        ("3D/3dmodel.model", b"<junk/>"),
        (
            "[Content_Types].xml",
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="model" ContentType="text/plain"/>'
            b"</Types>",
        ),
        (
            "_rels/.rels",
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rel0" Target="/3D/3dmodel.model" Type="https://example.invalid/wrong"/>'
            b"</Relationships>",
        ),
        (
            "3D/3dmodel.model",
            b'<model xmlns="https://example.invalid/not-3mf"><resources/><build/></model>',
        ),
    ],
)
def test_slice_rejects_well_formed_but_semantically_invalid_required_package_xml(tmp_path, monkeypatch, part, payload):
    def fake_run(command, **_kwargs):
        _write_artifact(command, structure_overrides={part: payload})
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "invalid_package"
    assert failure.fallback_eligible is True


@pytest.mark.parametrize(
    ("target", "extra_attribute"),
    [
        ("../3D/3dmodel.model", ""),
        ("/../3D/3dmodel.model", ""),
        ("https://example.invalid/3D/3dmodel.model", ""),
        ("//example.invalid/3D/3dmodel.model", ""),
        ("///3D/3dmodel.model", ""),
        ("3D%2F3dmodel.model", ""),
        ("3D%2F..%2F3D%2F3dmodel.model", ""),
        ("3D/3dmodel.model?", ""),
        ("3D/3dmodel.model#", ""),
        (" 3D/3dmodel.model", ""),
        ("3D/3dmodel.model ", ""),
        ("3D/3dmodel.model", ' TargetMode="External"'),
    ],
)
def test_slice_rejects_external_or_escaping_3mf_model_relationship_targets(
    tmp_path, monkeypatch, target, extra_attribute
):
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rel0" Target="{target}"{extra_attribute} '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        "</Relationships>"
    ).encode()

    def fake_run(command, **_kwargs):
        _write_artifact(command, structure_overrides={"_rels/.rels": relationships})
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "invalid_package"


def test_slice_accepts_override_content_binding_and_relative_internal_model_target(tmp_path, monkeypatch):
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Override PartName="/3D/3dmodel.model" '
        'ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        "</Types>"
    ).encode()
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rel0" Target="3D/3dmodel.model" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        "</Relationships>"
    ).encode()

    def fake_run(command, **_kwargs):
        _write_artifact(
            command,
            structure_overrides={
                "[Content_Types].xml": content_types,
                "_rels/.rels": relationships,
            },
        )
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    artifact = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert not isinstance(artifact, EngineFailure)
    assert artifact.direct_print_eligible is True


def test_slice_bounds_required_xml_before_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.engines.bambu.MAX_REQUIRED_XML_BYTES", 32, raising=False)

    def fake_run(command, **_kwargs):
        _write_artifact(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "archive_limit_exceeded"


@pytest.mark.parametrize(
    ("limit_name", "limit"),
    [
        ("MAX_ARCHIVE_BYTES", 16),
        ("MAX_ARCHIVE_MEMBERS", 3),
        ("MAX_MEMBER_UNCOMPRESSED_BYTES", 32),
        ("MAX_TOTAL_UNCOMPRESSED_BYTES", 64),
    ],
)
def test_slice_enforces_archive_and_member_resource_limits(tmp_path, monkeypatch, limit_name, limit):
    monkeypatch.setattr(f"app.services.engines.bambu.{limit_name}", limit, raising=False)

    def fake_run(command, **_kwargs):
        _write_artifact(command)
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "archive_limit_exceeded"


def test_slice_rejects_an_excessive_archive_compression_ratio(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.engines.bambu.MAX_COMPRESSION_RATIO", 2, raising=False)
    repeated = (
        "; total filament weight [g] : 6.25\n"
        "; total estimated time: 1h 2m\n"
        "; total layer number: 123\n" + "; repeated gcode\n" * 500
    )

    def fake_run(command, **_kwargs):
        _write_artifact(command, plates={"Metadata/plate_1.gcode": repeated})
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "archive_limit_exceeded"


def test_slice_validates_crc_before_accepting_the_native_artifact(tmp_path, monkeypatch):
    def fake_run(command, **_kwargs):
        output = _write_artifact(command, compression=zipfile.ZIP_STORED)
        payload = output.read_bytes()
        original = VALID_GCODE.encode("utf-8")
        assert original in payload
        output.write_bytes(payload.replace(original, b"X" + original[1:], 1))
        return _Proc()

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), tmp_path / "workspace", _options())

    assert isinstance(failure, EngineFailure)
    assert failure.code == "invalid_output"


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("layer_height", "NaN"),
        ("perimeters", "Infinity"),
        ("top_solid_layers", []),
        ("bottom_solid_layers", -1),
        ("infill_percent", "not-a-percent"),
        ("infill_pattern", {"pattern": "gyroid"}),
        ("brim_width", "-Infinity"),
        ("supports", "tree-auto"),
        ("multicolor", {"truthy": True}),
        ("use_embedded_settings", object()),
    ],
)
def test_slice_rejects_malformed_engine_neutral_options_before_probe(tmp_path, monkeypatch, option, value):
    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("malformed options must not probe or run Bambu Studio"),
    )

    with pytest.raises(RequestValidationError) as error:
        BambuEngine("AppRun", _Resolver()).slice(
            _model(tmp_path),
            tmp_path / "workspace",
            _options(**{option: value}),
        )

    assert error.value.code == "invalid_slicer_option"
    assert error.value.fallback_eligible is False


@pytest.mark.parametrize("nozzle", [Decimal("NaN"), Decimal("Infinity")])
def test_slice_rejects_non_finite_nozzle_as_invalid_terminal_input(tmp_path, monkeypatch, nozzle):
    monkeypatch.setattr(
        "app.services.engines.bambu.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail("invalid nozzle must not probe or run Bambu Studio"),
    )

    with pytest.raises(RequestValidationError) as error:
        BambuEngine("AppRun", _Resolver()).slice(
            _model(tmp_path),
            tmp_path / "workspace",
            replace(_options(), nozzle_diameter=nozzle),
        )

    assert error.value.code == "invalid_nozzle"


@pytest.mark.parametrize("outcome", ["timeout", "nonzero"])
def test_slice_discards_partial_artifacts_after_failed_execution(tmp_path, monkeypatch, outcome):
    workspace = tmp_path / "workspace"

    def fake_run(command, **_kwargs):
        _write_artifact(command)
        if outcome == "timeout":
            raise subprocess.TimeoutExpired("AppRun", 600)
        return _Proc(returncode=2)

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), workspace, _options())

    assert isinstance(failure, EngineFailure)
    assert not (workspace / "rainbow-dragon.gcode.3mf").exists()


def test_slice_redacts_actual_unix_and_windows_paths_from_stderr(tmp_path, monkeypatch):
    workspace = tmp_path / "secret-workspace"

    def fake_run(_command, **_kwargs):
        return _Proc(
            returncode=3,
            stderr=f"failed at {workspace}/plate.gcode and C:\\private\\request\\model.stl".encode(),
        )

    monkeypatch.setattr("app.services.engines.bambu.subprocess.run", _versioned_runner(fake_run))

    failure = BambuEngine("AppRun", _Resolver()).slice(_model(tmp_path), workspace, _options())

    assert isinstance(failure, EngineFailure)
    diagnostic = str(failure.diagnostics)
    assert str(workspace) not in diagnostic
    assert "C:\\private\\request" not in diagnostic
