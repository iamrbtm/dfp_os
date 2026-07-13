"""3MF container load/save with paint-preserving build rewrites.

Paint data (per-triangle ``paint_color`` / ``mmu_segmentation`` attributes) lives
in ``<resources>``. To guarantee zero paint loss, saving never reserializes the
model XML with ElementTree; it copies every zip entry byte-for-byte and only
splices a freshly generated ``<build>`` section into ``3D/3dmodel.model`` via
string-level surgery.
"""

from __future__ import annotations

import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PRODUCTION_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
PAINT_ATTRS = ("paint_color", "mmu_segmentation")

PRIMARY_MODEL = "3D/3dmodel.model"


def _is_project_entry(name: str) -> bool:
    """Whether a zip entry holds slicer printer/project profiles (not paint).

    Paint lives in ``3D/*.model``; printer + project settings and thumbnails
    live under ``Metadata/`` and ``Auxiliaries/``. Passing those through makes a
    slicer open the packed file on the source machine's printer/bed.
    """
    return name.startswith(("Metadata/", "Auxiliaries/"))


# Drop predicate for :meth:`ThreeMF.save` that strips embedded project settings.
PROJECT_ENTRY_PREDICATE = _is_project_entry

# The Orca/Bambu project profile (bed, filament colours). Kept + bed-patched by
# the default surgical save so the packed file opens on the packed bed with its
# colours intact.
PROJECT_SETTINGS_ENTRY = "Metadata/project_settings.config"


def _is_stale_entry(name: str) -> bool:
    """Whether a zip entry is a stale plate artifact from the source layout.

    These depict the OLD pre-pack plate (slice results, cut lines, plate/preview
    thumbnails) and are meaningless once the parts are re-nested, so the default
    save drops them -- unlike colour-bearing ``model_settings.config`` /
    ``project_settings.config``, which are kept.
    """
    if not name.startswith("Metadata/"):
        return False
    if name in ("Metadata/slice_info.config", "Metadata/cut_information.xml"):
        return True
    return name.lower().endswith(".png")


# Drop predicate for the default surgical save: stale plate artifacts only.
STALE_ENTRY_PREDICATE = _is_stale_entry


def _fmt_bed(v: float) -> str:
    """Format a bed dimension the way Orca does (``%g``: no trailing ``.0``)."""
    return f"{float(v):g}"


def patch_project_settings_bed(
    data: bytes, bed_w: float, bed_d: float
) -> bytes | None:
    """Return ``project_settings.config`` bytes with ``printable_area`` set to the
    packed bed's corners (``["0x0", "Wx0", "WxD", "0xD"]``), or ``None`` if the
    payload is not JSON we can parse. ``printable_height`` is left untouched.
    """
    try:
        obj = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    w, d = _fmt_bed(bed_w), _fmt_bed(bed_d)
    obj["printable_area"] = ["0x0", f"{w}x0", f"{w}x{d}", f"0x{d}"]
    return json.dumps(obj, ensure_ascii=False, indent=4).encode("utf-8")


# --------------------------------------------------------------------------- #
# Native Snapmaker U1 project profile (colour transplant)
# --------------------------------------------------------------------------- #

# Sanitized native U1 ``project_settings`` template (see
# scripts/extract-u1-template.py). Loaded from a real file next to this module so
# the same path works both for the installed package and the browser copy that
# build.sh drops under web-public/py/multipack/data/.
_U1_TEMPLATE_PATH = Path(__file__).parent / "data" / "u1_project_settings.json"

# The U1 has four toolheads: the template's per-filament arrays carry one entry
# per slot, and a source with N filaments extends every array to N.
_U1_FILAMENT_SLOTS = 4


def _load_u1_template() -> dict:
    """Load the packaged native U1 ``project_settings`` template as a dict."""
    return json.loads(_U1_TEMPLATE_PATH.read_text(encoding="utf-8"))


def _norm_filament_colour(value: object) -> str:
    """Uppercase ``#RRGGBB`` / ``#RRGGBBAA`` as the U1 template stores colours."""
    s = str(value).strip()
    if not s.startswith("#"):
        s = "#" + s
    return "#" + s[1:].upper()


def _resize_list(values: list, n: int) -> list:
    """Repeat the last element / truncate so ``values`` has length ``n``."""
    if not values:
        return values
    if len(values) >= n:
        return list(values[:n])
    return list(values) + [values[-1]] * (n - len(values))


def u1_project_settings(
    source_settings_bytes: bytes | None,
    bed_w: float,
    bed_d: float,
    n_filaments_hint: int | None = None,
) -> bytes:
    """Native Snapmaker U1 ``project_settings.config`` bytes for a packed plate.

    Starts from the packaged U1 template and transplants the SOURCE file's
    ``filament_colour`` (and ``filament_type`` when present) so the packed file
    opens as a native U1 project keeping the model's colours. The number of
    filament slots N is ``max(len(source colours), n_filaments_hint, 4)``; every
    ``filament_*`` array in the template is extended/truncated to N (repeating
    the last element) *before* the source colours/types are overlaid so the
    per-filament arrays stay consistent. The bed is patched to ``bed_w`` x
    ``bed_d`` via :func:`patch_project_settings_bed`.

    ``source_settings_bytes`` may be ``None`` or non-JSON (a plain 3MF): the
    template is emitted with only the bed patched, so plain files still gain a
    U1 profile.
    """
    template = _load_u1_template()

    source: dict | None = None
    if source_settings_bytes is not None:
        try:
            parsed = json.loads(source_settings_bytes.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            source = parsed

    src_colours: list[str] = []
    src_types: list | None = None
    if source is not None:
        raw_colours = source.get("filament_colour")
        if isinstance(raw_colours, list):
            src_colours = [_norm_filament_colour(c) for c in raw_colours]
        raw_types = source.get("filament_type")
        if isinstance(raw_types, list):
            src_types = list(raw_types)

    n = max(len(src_colours), n_filaments_hint or 0, _U1_FILAMENT_SLOTS)

    # Resize every per-filament array first so the transplant lands on a
    # consistent N-slot profile.
    for key, value in list(template.items()):
        if key.startswith("filament_") and isinstance(value, list):
            template[key] = _resize_list(value, n)

    if src_colours:
        template["filament_colour"] = _resize_list(src_colours, n)
    if src_types:
        template["filament_type"] = _resize_list(src_types, n)

    merged = json.dumps(template, ensure_ascii=False, indent=4).encode("utf-8")
    patched = patch_project_settings_bed(merged, bed_w, bed_d)
    return patched if patched is not None else merged


# Distinct paint attribute values (paint_color / mmu_segmentation) in a model.
_PAINT_VALUE_RE = re.compile(rb'(?:paint_color|mmu_segmentation)="([^"]*)"')

Transform = tuple  # 12 floats, 3MF row-major 4x3

# --------------------------------------------------------------------------- #
# Namespace-agnostic XML helpers
# --------------------------------------------------------------------------- #


def _local(tag: str) -> str:
    """Local name of a possibly namespaced tag/attribute key."""
    return tag.rsplit("}", 1)[-1]


def _attr(elem: ET.Element, name: str) -> str | None:
    """Attribute value matched by local name (namespace-agnostic)."""
    for key, value in elem.attrib.items():
        if _local(key) == name:
            return value
    return None


def _find(elem: ET.Element, name: str) -> ET.Element | None:
    for child in elem:
        if _local(child.tag) == name:
            return child
    return None


def _findall(elem: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in elem if _local(child.tag) == name]


def _norm_entry(path: str) -> str:
    """Normalise a 3MF part path to a zip entry name (strip leading slash)."""
    return path.lstrip("/")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class ModelObject:
    object_id: str
    vertices: list[tuple[float, float, float]]
    triangle_count: int
    has_paint: bool


@dataclass
class BuildItem:
    object_id: str
    transform: Transform | None = None


@dataclass
class _RawMesh:
    vertices: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]
    has_paint: bool


@dataclass
class _RawComponents:
    # (objectid, path or None, transform or None)
    components: list[tuple[str, str | None, Transform | None]]


# --------------------------------------------------------------------------- #
# Transform helpers
#
# 3MF transform = 12 space-separated floats, row-major 4x3:
#   (m00 m01 m02) X axis, (m10 m11 m12) Y axis, (m20 m21 m22) Z axis,
#   (m30 m31 m32) translation. Points transform as row vectors: p' = [x y z 1]·M.
# --------------------------------------------------------------------------- #


IDENTITY: Transform = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


def compose_transform(
    scale: float, rot_z_deg: float, tx: float, ty: float, tz: float
) -> Transform:
    """Uniform scale + rotation about Z + translation as a 12-float transform."""
    theta = math.radians(rot_z_deg)
    c = math.cos(theta) * scale
    s = math.sin(theta) * scale
    return (
        c, s, 0.0,      # X axis row
        -s, c, 0.0,     # Y axis row
        0.0, 0.0, scale,  # Z axis row
        float(tx), float(ty), float(tz),  # translation
    )


def compose_affine(a: Transform, b: Transform) -> Transform:
    """Compose two 3MF transforms as row-vector ops: apply ``a``, then ``b``.

    Points transform as row vectors (``p' = p·M``), so applying ``a`` then ``b``
    is ``p·Ma·Mb``. The 3x3 linear blocks multiply (``R = Ra·Rb``) and ``a``'s
    translation is carried through ``b``'s linear part (``t = ta·Rb + tb``).
    Exactly equivalent to ``apply_transform(apply_transform(pts, a), b)``.
    Composing with :data:`IDENTITY` as ``a`` returns ``b`` unchanged.
    """
    a00, a01, a02, a10, a11, a12, a20, a21, a22, a30, a31, a32 = a
    b00, b01, b02, b10, b11, b12, b20, b21, b22, b30, b31, b32 = b
    return (
        a00 * b00 + a01 * b10 + a02 * b20,
        a00 * b01 + a01 * b11 + a02 * b21,
        a00 * b02 + a01 * b12 + a02 * b22,
        a10 * b00 + a11 * b10 + a12 * b20,
        a10 * b01 + a11 * b11 + a12 * b21,
        a10 * b02 + a11 * b12 + a12 * b22,
        a20 * b00 + a21 * b10 + a22 * b20,
        a20 * b01 + a21 * b11 + a22 * b21,
        a20 * b02 + a21 * b12 + a22 * b22,
        a30 * b00 + a31 * b10 + a32 * b20 + b30,
        a30 * b01 + a31 * b11 + a32 * b21 + b31,
        a30 * b02 + a31 * b12 + a32 * b22 + b32,
    )


def apply_transform(
    vertices: list[tuple[float, float, float]], T: Transform
) -> list[tuple[float, float, float]]:
    m00, m01, m02, m10, m11, m12, m20, m21, m22, m30, m31, m32 = T
    out: list[tuple[float, float, float]] = []
    for x, y, z in vertices:
        out.append(
            (
                x * m00 + y * m10 + z * m20 + m30,
                x * m01 + y * m11 + z * m21 + m31,
                x * m02 + y * m12 + z * m22 + m32,
            )
        )
    return out


def bounding_box(
    vertices: list[tuple[float, float, float]]
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if not vertices:
        raise ValueError("bounding_box of empty vertex list")
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


# --------------------------------------------------------------------------- #
# Float formatting (compact, no scientific notation)
# --------------------------------------------------------------------------- #


def _fmt_float(v: float) -> str:
    v = float(v)
    if v == 0.0:
        return "0"
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s


# --------------------------------------------------------------------------- #
# Build-section surgery
# --------------------------------------------------------------------------- #

# Attribute values may legally contain ">" or "/>": skip quoted spans.
_BUILD_OPEN = re.compile(r"<build\b(?:\"[^\"]*\"|'[^']*'|[^>\"'])*?(/?)>", re.DOTALL)


def _tag_open_re(tag: str) -> re.Pattern:
    """Quoted-span-aware regex matching a ``<tag ...>`` (or ``<tag/>``) open tag.

    Group 1 captures the self-closing ``/`` (empty otherwise)."""
    return re.compile(
        rf"<{tag}\b(?:\"[^\"]*\"|'[^']*'|[^>\"'])*?(/?)>", re.DOTALL
    )


def _first_block(text: str, tag: str) -> tuple[int, int, str] | None:
    """Span ``(start, end, source)`` of the first ``<tag>...</tag>`` element
    (or self-closing ``<tag/>``) in *text*, or ``None`` if absent."""
    m = _tag_open_re(tag).search(text)
    if not m:
        return None
    if m.group(1) == "/":
        return m.start(), m.end(), m.group(0)
    close = text.find(f"</{tag}>", m.end())
    if close == -1:
        return m.start(), m.end(), m.group(0)
    end = close + len(f"</{tag}>")
    return m.start(), end, text[m.start():end]


def _build_open_attrs(open_tag: str) -> tuple[str, bool]:
    """``(attrs, has_uuid)`` for a matched ``<build ...>`` open tag.

    ``attrs`` is spliced straight back after ``<build`` so the packed build keeps
    the source's attributes verbatim (notably the production ``p:UUID`` that
    Bambu-lineage loaders key instances on). ``has_uuid`` gates per-item UUIDs."""
    inner = open_tag[len("<build"):-1]  # strip '<build' and trailing '>'
    if inner.endswith("/"):  # self-closing <build/>
        inner = inner[:-1]
    attrs = (" " + inner.strip()) if inner.strip() else ""
    has_uuid = re.search(r"\bUUID\s*=", inner) is not None
    return attrs, has_uuid


def _item_uuid(i: int) -> str:
    """Deterministic per-item production UUID for the *i*-th build item."""
    return f"{i + 1:08d}-71b2-4a10-8041-{i + 1:012d}"


def _render_build(items: list[BuildItem], attrs: str = "", uuids: bool = False) -> str:
    lines = [f"<build{attrs}>"]
    for i, it in enumerate(items):
        a = f' objectid="{it.object_id}"'
        if it.transform is not None:
            ts = " ".join(_fmt_float(v) for v in it.transform)
            a += f' transform="{ts}"'
        if uuids:
            a += f' p:UUID="{_item_uuid(i)}"'
        lines.append(f"  <item{a}/>")
    lines.append("</build>")
    return "\n".join(lines)


def _replace_build(xml_text: str, items: list[BuildItem]) -> str:
    m = _BUILD_OPEN.search(xml_text)
    if not m:
        raise ValueError("model XML has no <build> element")
    attrs, has_uuid = _build_open_attrs(m.group(0))
    new_build = _render_build(items, attrs, has_uuid)
    if m.group(1) == "/":  # self-closing <build/>
        start, end = m.start(), m.end()
    else:
        close = xml_text.find("</build>", m.end())
        if close == -1:
            raise ValueError("unterminated <build> element")
        start, end = m.start(), close + len("</build>")
    return xml_text[:start] + new_build + xml_text[end:]


# --------------------------------------------------------------------------- #
# model_settings.config rewrite (keep <object>s verbatim; rebuild plate/assemble)
# --------------------------------------------------------------------------- #

# Bambu Metadata part that mirrors <build> instances. Orca reconciles it against
# <build>; a stale single-instance config (plus dangling thumbnail refs to pngs
# we drop) makes Orca discard the config and fall back to default colours.
MODEL_SETTINGS_ENTRY = "Metadata/model_settings.config"

# Plate metadata pointing at stale plate/preview pngs (dropped as stale entries).
_DROP_PLATE_KEYS = (
    "thumbnail_file",
    "thumbnail_no_light_file",
    "top_file",
    "pick_file",
)
_META_TAG = re.compile(r'<metadata\b(?:"[^"]*"|\'[^\']*\'|[^>"\'])*?/>', re.DOTALL)
_MODEL_INSTANCE_BLOCK = re.compile(
    r"<model_instance\b.*?</model_instance>", re.DOTALL
)


def _tag_attr_value(tag: str, name: str) -> str | None:
    m = re.search(rf'\b{re.escape(name)}\s*=\s*"([^"]*)"', tag)
    return m.group(1) if m else None


def _build_plate(block: str, items: list[BuildItem]) -> str:
    """Rebuild a ``<plate>`` block: keep its simple metadata (minus stale
    thumbnail refs), then one ``<model_instance>`` per saved build item."""
    body = _MODEL_INSTANCE_BLOCK.sub("", block)
    lines = ["  <plate>"]
    for m in _META_TAG.finditer(body):
        tag = m.group(0)
        if _tag_attr_value(tag, "key") in _DROP_PLATE_KEYS:
            continue
        lines.append(f"    {tag.strip()}")
    for idx, it in enumerate(items):
        lines.append("    <model_instance>")
        lines.append(f'      <metadata key="object_id" value="{it.object_id}"/>')
        lines.append(f'      <metadata key="instance_id" value="{idx}"/>')
        lines.append(f'      <metadata key="identify_id" value="{100 + idx}"/>')
        lines.append("    </model_instance>")
    lines.append("  </plate>")
    return "\n".join(lines)


def _build_assemble(items: list[BuildItem]) -> str:
    """Rebuild an ``<assemble>`` block: one item per saved build item, each
    carrying that instance's final transform."""
    lines = ["  <assemble>"]
    for idx, it in enumerate(items):
        ts = (
            " ".join(_fmt_float(v) for v in it.transform)
            if it.transform is not None
            else ""
        )
        lines.append(
            f'   <assemble_item object_id="{it.object_id}" instance_id="{idx}" '
            f'transform="{ts}" offset="0 0 0"/>'
        )
    lines.append("  </assemble>")
    return "\n".join(lines)


def _rewrite_model_settings(text: str, items: list[BuildItem]) -> str:
    """Rewrite ``model_settings.config`` for the packed instances: every
    ``<object>`` block is kept byte-for-byte (extruder/part metadata intact);
    only ``<plate>`` and ``<assemble>`` are regenerated to declare one instance
    per build item. Files with neither block pass through unchanged."""
    plate = _first_block(text, "plate")
    if plate is not None:
        start, end, block = plate
        text = text[:start] + _build_plate(block, items) + text[end:]
    asm = _first_block(text, "assemble")
    if asm is not None:
        start, end, _block = asm
        text = text[:start] + _build_assemble(items) + text[end:]
    return text


# --------------------------------------------------------------------------- #
# ThreeMF
# --------------------------------------------------------------------------- #


@dataclass
class ThreeMF:
    objects: dict[str, ModelObject] = field(default_factory=dict)
    build_items: list[BuildItem] = field(default_factory=list)
    # internal
    _source_path: str = ""
    _model_name: str = PRIMARY_MODEL
    _raw: dict[str, dict[str, _RawMesh | _RawComponents]] = field(
        default_factory=dict
    )

    # -- loading ----------------------------------------------------------- #

    @classmethod
    def load(cls, path: str) -> "ThreeMF":
        self = cls(_source_path=str(path))
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            self._model_name = _primary_model_name(zf, names)
            # Parse every model part; components may reference any of them.
            for name in names:
                if name.lower().endswith(".model"):
                    data = zf.read(name)
                    self._raw[name] = _parse_model_resources(data)
            main = self._raw.get(self._model_name, {})
            for oid in main:
                verts, tri_count, has_paint = self._resolve(
                    self._model_name, oid, set()
                )
                self.objects[oid] = ModelObject(
                    object_id=oid,
                    vertices=verts,
                    triangle_count=tri_count,
                    has_paint=has_paint,
                )
            self.build_items = _parse_build(zf.read(self._model_name))
        return self

    def _resolve(
        self, model_name: str, oid: str, visited: set[tuple[str, str]]
    ) -> tuple[list[tuple[float, float, float]], int, bool]:
        key = (model_name, oid)
        if key in visited:
            return [], 0, False
        visited = visited | {key}
        raw = self._raw.get(model_name, {}).get(oid)
        if raw is None:
            return [], 0, False
        if isinstance(raw, _RawMesh):
            return list(raw.vertices), len(raw.triangles), raw.has_paint
        # components
        verts: list[tuple[float, float, float]] = []
        tri_count = 0
        has_paint = False
        for cid, cpath, ctransform in raw.components:
            target = _norm_entry(cpath) if cpath else model_name
            cv, ctc, chp = self._resolve(target, cid, visited)
            if ctransform is not None:
                cv = apply_transform(cv, ctransform)
            verts.extend(cv)
            tri_count += ctc
            has_paint = has_paint or chp
        return verts, tri_count, has_paint

    # -- saving ------------------------------------------------------------ #

    def save(
        self,
        path: str,
        items: list[BuildItem],
        *,
        drop_entries: Callable[[str], bool] | None = None,
        replace_entries: dict[str, bytes] | None = None,
    ) -> None:
        """Write a new zip: every entry byte-identical except the primary model,
        whose <build> span alone is replaced with the given items.

        ``drop_entries`` is an optional predicate on entry names; entries it
        matches are omitted from the output. ``replace_entries`` maps entry names
        to replacement bytes written verbatim in place of the original. When both
        target the same name, replace wins (the entry is kept, with new bytes).
        Both default to ``None`` -- copies every entry byte-for-byte.

        Re-reads the source 3MF, so it must still exist at its load-time path.
        """
        unknown = sorted({it.object_id for it in items} - set(self.objects))
        if unknown:
            raise ValueError(
                f"build items reference unknown object ids: {', '.join(unknown)}"
            )
        try:
            with zipfile.ZipFile(self._source_path, "r") as zf:
                entries = [(info, zf.read(info.filename)) for info in zf.infolist()]
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"source 3MF no longer exists at {self._source_path!r}; "
                "save() re-reads the file it was loaded from"
            ) from e

        replace = replace_entries or {}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
            for info, data in entries:
                name = info.filename
                if name in replace:
                    data = replace[name]
                elif drop_entries is not None and drop_entries(name):
                    continue
                elif name == self._model_name:
                    text = data.decode("utf-8")
                    data = _replace_build(text, items).encode("utf-8")
                out.writestr(info, data)

    def _read_source_entry(self, name: str) -> bytes | None:
        """Raw bytes of a source-zip entry, or ``None`` if absent/unreadable."""
        try:
            with zipfile.ZipFile(self._source_path, "r") as zf:
                return zf.read(name)
        except (FileNotFoundError, KeyError):
            return None

    def surgical_save_kwargs(
        self,
        bed_w: float,
        bed_d: float,
        items: list[BuildItem],
        printer: str = "u1",
    ) -> dict:
        """``save`` kwargs for the default packed output.

        ``printer="u1"`` (default) replaces ``project_settings.config`` with a
        native Snapmaker U1 profile (via :func:`u1_project_settings`) carrying
        the source file's transplanted filament colours/types, so the packed
        file opens as a native U1 project. ``printer="source"`` keeps the source
        profile and only patches its bed to the packed ``bed_w`` x ``bed_d`` (the
        file opens on the source printer). Either way the colour-bearing Metadata
        and Auxiliaries are kept and only stale plate artifacts are dropped.

        Also rewrites ``model_settings.config`` (when present) so its
        ``<plate>``/``<assemble>`` declare one instance per build item in
        ``items`` -- otherwise Orca sees N build items vs 1 declared instance
        (plus dangling thumbnail refs to the pngs we drop), discards the config,
        and falls back to default colours. Every ``<object>`` block is preserved
        byte-for-byte so per-object extruder/part metadata (the source filament
        order / indices) is untouched.
        """
        replace: dict[str, bytes] = {}
        data = self._read_source_entry(PROJECT_SETTINGS_ENTRY)
        if printer == "u1":
            replace[PROJECT_SETTINGS_ENTRY] = u1_project_settings(
                data, bed_w, bed_d
            )
        elif data is not None:
            patched = patch_project_settings_bed(data, bed_w, bed_d)
            if patched is not None:
                replace[PROJECT_SETTINGS_ENTRY] = patched
        ms = self._read_source_entry(MODEL_SETTINGS_ENTRY)
        if ms is not None:
            try:
                text = ms.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is not None:
                replace[MODEL_SETTINGS_ENTRY] = _rewrite_model_settings(
                    text, items
                ).encode("utf-8")
        return {
            "drop_entries": STALE_ENTRY_PREDICATE,
            "replace_entries": replace or None,
        }

    def paint_color_count(self) -> int:
        """Number of distinct paint attribute values across all model parts.

        Counts distinct ``paint_color`` / ``mmu_segmentation`` attribute values
        via a byte-level regex over every ``*.model`` part -- a cheap proxy for
        how many colors a painted part uses, used to size the auto prime tower.
        All ``.model`` parts are scanned (not just the primary) so production-
        extension files, whose paint lives in ``3D/Objects/*.model`` sub-parts,
        are counted correctly.
        """
        values: set[bytes] = set()
        try:
            with zipfile.ZipFile(self._source_path, "r") as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".model"):
                        values.update(_PAINT_VALUE_RE.findall(zf.read(name)))
        except (FileNotFoundError, KeyError):
            return 0
        return len(values)


# --------------------------------------------------------------------------- #
# Model-part parsing
# --------------------------------------------------------------------------- #


def _primary_model_name(zf: zipfile.ZipFile, names: set[str]) -> str:
    if PRIMARY_MODEL in names:
        return PRIMARY_MODEL
    # Resolve StartPart from _rels/.rels if the conventional name is absent.
    if "_rels/.rels" in names:
        try:
            root = ET.fromstring(zf.read("_rels/.rels"))
        except ET.ParseError:
            root = None
        if root is not None:
            for rel in root:
                rtype = _attr(rel, "Type") or ""
                target = _attr(rel, "Target")
                if target and rtype.endswith("3dmodel"):
                    entry = _norm_entry(target)
                    if entry in names:
                        return entry
    for name in sorted(names):
        if name.lower().endswith(".model"):
            return name
    return PRIMARY_MODEL


def _parse_model_resources(data: bytes) -> dict[str, _RawMesh | _RawComponents]:
    root = ET.fromstring(data)
    resources = _find(root, "resources")
    out: dict[str, _RawMesh | _RawComponents] = {}
    if resources is None:
        return out
    for obj in _findall(resources, "object"):
        oid = _attr(obj, "id")
        if oid is None:
            continue
        mesh = _find(obj, "mesh")
        if mesh is not None:
            out[oid] = _parse_mesh(mesh)
            continue
        comps = _find(obj, "components")
        if comps is not None:
            out[oid] = _parse_components(comps)
    return out


def _parse_mesh(mesh: ET.Element) -> _RawMesh:
    vertices: list[tuple[float, float, float]] = []
    verts_el = _find(mesh, "vertices")
    if verts_el is not None:
        for v in _findall(verts_el, "vertex"):
            vertices.append(
                (
                    float(_attr(v, "x") or 0.0),
                    float(_attr(v, "y") or 0.0),
                    float(_attr(v, "z") or 0.0),
                )
            )
    triangles: list[tuple[int, int, int]] = []
    has_paint = False
    tris_el = _find(mesh, "triangles")
    if tris_el is not None:
        for t in _findall(tris_el, "triangle"):
            triangles.append(
                (
                    int(_attr(t, "v1") or 0),
                    int(_attr(t, "v2") or 0),
                    int(_attr(t, "v3") or 0),
                )
            )
            if not has_paint:
                if any(_local(k) in PAINT_ATTRS for k in t.attrib):
                    has_paint = True
    return _RawMesh(vertices=vertices, triangles=triangles, has_paint=has_paint)


def _parse_components(comps: ET.Element) -> _RawComponents:
    out: list[tuple[str, str | None, Transform | None]] = []
    for c in _findall(comps, "component"):
        cid = _attr(c, "objectid")
        if cid is None:
            continue
        cpath = _attr(c, "path")
        ctransform = _parse_transform(_attr(c, "transform"))
        out.append((cid, cpath, ctransform))
    return _RawComponents(components=out)


def _parse_transform(text: str | None) -> Transform | None:
    if not text:
        return None
    parts = text.split()
    if len(parts) != 12:
        return None
    return tuple(float(p) for p in parts)


def _parse_build(data: bytes) -> list[BuildItem]:
    root = ET.fromstring(data)
    build = _find(root, "build")
    items: list[BuildItem] = []
    if build is None:
        return items
    for item in _findall(build, "item"):
        oid = _attr(item, "objectid")
        if oid is None:
            continue
        items.append(
            BuildItem(object_id=oid, transform=_parse_transform(_attr(item, "transform")))
        )
    return items
