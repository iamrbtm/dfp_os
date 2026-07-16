from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

import pytest

from pmp import NestError, pack_model_bytes
from pmp.stl import load


def _binary_tetrahedron(*, solid_header: bool = False) -> bytes:
    header = (b"solid misleading" if solid_header else b"binary tetrahedron").ljust(80, b"\0")
    triangles = [
        ((0, 0, 0), (20, 0, 0), (0, 20, 0)),
        ((0, 0, 0), (0, 20, 0), (0, 0, 10)),
        ((0, 0, 0), (0, 0, 10), (20, 0, 0)),
        ((20, 0, 0), (0, 0, 10), (0, 20, 0)),
    ]
    data = header + struct.pack("<I", len(triangles))
    for triangle in triangles:
        data += struct.pack("<12fH", 0, 0, 1, *triangle[0], *triangle[1], *triangle[2], 0)
    return data


def test_stl_loader_prefers_valid_binary_length_even_with_solid_header():
    mesh = load(_binary_tetrahedron(solid_header=True))

    assert mesh.source_format == "binary_stl"
    assert len(mesh.triangles) == 4


def test_pmp_packs_stl_and_adds_u1_project_settings():
    result = pack_model_bytes(
        _binary_tetrahedron(),
        "tetrahedron.stl",
        target=None,
        count=2,
        bed_w=100,
        bed_d=100,
        pack_mode="hull",
        printer="u1",
    )
    output = Path(result["out_path"])
    try:
        assert result["placed"] == 2
        assert result["scale"] == 1.0
        with zipfile.ZipFile(output) as archive:
            settings = json.loads(archive.read("Metadata/project_settings.config"))
            assert settings["printable_area"] == ["0x0", "100x0", "100x100", "0x100"]
    finally:
        output.unlink(missing_ok=True)


def test_pmp_rejects_unsupported_asset_format():
    with pytest.raises(NestError, match="supports STL and 3MF"):
        pack_model_bytes(b"model", "model.obj")
