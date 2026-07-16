"""Bounded STL loading and minimal 3MF generation for PMP."""

from __future__ import annotations

import io
import math
import struct
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

MAX_TRIANGLES = 2_000_000


@dataclass(frozen=True)
class STLMesh:
    vertices: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]
    source_format: str


def _indexed(triangles, source_format: str) -> STLMesh:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    indexes: dict[tuple[float, float, float], int] = {}
    for triangle in triangles:
        face = []
        for raw in triangle:
            vertex = tuple(float(value) for value in raw)
            if not all(math.isfinite(value) for value in vertex):
                raise ValueError("STL contains a non-finite coordinate")
            index = indexes.get(vertex)
            if index is None:
                index = len(vertices)
                indexes[vertex] = index
                vertices.append(vertex)
            face.append(index)
        if len(set(face)) == 3:
            faces.append(tuple(face))
    if not faces:
        raise ValueError("STL contains no non-degenerate triangles")
    return STLMesh(vertices, faces, source_format)


def load(data: bytes) -> STLMesh:
    """Read binary or ASCII STL, preferring binary length validation."""
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        expected = 84 + count * 50
        if count and count <= MAX_TRIANGLES and expected == len(data):
            triangles = []
            for offset in range(84, expected, 50):
                values = struct.unpack_from("<12fH", data, offset)
                triangles.append((values[3:6], values[6:9], values[9:12]))
            return _indexed(triangles, "binary_stl")
        if count > MAX_TRIANGLES and expected == len(data):
            raise ValueError(f"STL exceeds the {MAX_TRIANGLES:,}-triangle limit")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("STL is neither valid binary nor ASCII") from exc
    triangles = []
    current = []
    for line in text.splitlines():
        parts = line.strip().split()
        if parts and parts[0].lower() == "vertex":
            if len(parts) != 4:
                raise ValueError("Malformed ASCII STL vertex")
            current.append(tuple(float(value) for value in parts[1:]))
            if len(current) == 3:
                triangles.append(tuple(current))
                current = []
                if len(triangles) > MAX_TRIANGLES:
                    raise ValueError(f"STL exceeds the {MAX_TRIANGLES:,}-triangle limit")
    if current:
        raise ValueError("Truncated ASCII STL triangle")
    return _indexed(triangles, "ascii_stl")


def to_3mf(mesh: STLMesh) -> bytes:
    """Create a standards-compliant, single-object 3MF container."""
    namespace = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
    ET.register_namespace("", namespace)
    model = ET.Element(f"{{{namespace}}}model", {"unit": "millimeter"})
    resources = ET.SubElement(model, f"{{{namespace}}}resources")
    obj = ET.SubElement(resources, f"{{{namespace}}}object", {"id": "1", "type": "model"})
    mesh_node = ET.SubElement(obj, f"{{{namespace}}}mesh")
    vertices = ET.SubElement(mesh_node, f"{{{namespace}}}vertices")
    for x, y, z in mesh.vertices:
        ET.SubElement(vertices, f"{{{namespace}}}vertex", {"x": f"{x:.9g}", "y": f"{y:.9g}", "z": f"{z:.9g}"})
    triangles = ET.SubElement(mesh_node, f"{{{namespace}}}triangles")
    for v1, v2, v3 in mesh.triangles:
        ET.SubElement(triangles, f"{{{namespace}}}triangle", {"v1": str(v1), "v2": str(v2), "v3": str(v3)})
    build = ET.SubElement(model, f"{{{namespace}}}build")
    ET.SubElement(build, f"{{{namespace}}}item", {"objectid": "1"})
    model_bytes = ET.tostring(model, encoding="utf-8", xml_declaration=True)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        archive.writestr("3D/3dmodel.model", model_bytes)
    return output.getvalue()
