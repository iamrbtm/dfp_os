"""Browser engine pipeline (Pyodide-friendly, no CLI deps).

This module reimplements the pieces of ``multipack.cli`` the public browser build
needs -- paint-preserving *nesting* and the *color-swap* analyzer -- without
importing ``multipack.cli`` (which pulls in Flask/webapp deps). It is plain
Python: it runs unchanged both natively under pytest and inside Pyodide's
in-memory filesystem.
"""

from __future__ import annotations

import tempfile
from collections import defaultdict
from pathlib import Path

from multipack import gcode, packing, threemf

# Same defaults as ``multipack.cli`` so browser output matches the CLI exactly.
DEFAULT_MARGIN = 3.5
DEFAULT_SPACING = 2.0
DEFAULT_ANGLE_STEP = 15.0


class NestError(Exception):
    """Recoverable nesting failure with a user-facing message."""


def _pick_source_object(model: threemf.ThreeMF) -> str:
    """Choose the object to pack (mirrors ``cli._pick_source_object``)."""
    with_geometry = [oid for oid, o in model.objects.items() if o.vertices]
    if not with_geometry:
        raise NestError("no object with geometry found in the 3MF")
    if len(with_geometry) == 1:
        return with_geometry[0]
    for item in model.build_items:
        if item.object_id in model.objects and model.objects[item.object_id].vertices:
            return item.object_id
    return with_geometry[0]


def _auto_tower(
    *, has_paint: bool, n_colors: int, bed_w: float, bed_d: float, margin: float
) -> tuple[float, float, float, float] | None:
    """Auto prime-tower rect flush to the (margin-inset) top-right corner.

    Sizing matches ``cli._parse_tower(spec="auto")`` exactly: a square of side
    ``min(60, 20 + 8 * n_colors)`` mm, reserved only when the part is painted.
    """
    if not has_paint:
        return None
    size = min(60.0, 20.0 + 8.0 * n_colors)
    x = max(margin, bed_w - margin - size)
    y = max(margin, bed_d - margin - size)
    return (x, y, size, size)


def nest_bytes(
    data: bytes,
    *,
    target: float | None = 50.0,
    spacing: float = DEFAULT_SPACING,
    bed_w: float = 270.0,
    bed_d: float = 270.0,
    count: int | None = None,
    angle_step: float = DEFAULT_ANGLE_STEP,
    pack_mode: str = "auto",
    tower: str = "auto",
    margin: float = DEFAULT_MARGIN,
    printer: str = "u1",
) -> dict:
    """Load, pack, and save a painted 3MF given its raw bytes.

    Writes ``data`` to a temp 3MF (kept alive so ``ThreeMF.save`` can re-read it),
    packs it, and saves a packed 3MF to a sibling temp path. With
    ``printer="u1"`` (default) the packed file opens as a native Snapmaker U1
    project carrying the source's filament colours; ``printer="source"`` keeps
    the source printer (only the bed is patched). Either way the colour-bearing
    metadata is kept and stale plate artifacts are dropped. Returns a dict with
    the SVG preview, stats, and the output path (whose bytes the caller reads
    back). Raises ``NestError``.
    """
    tmp = Path(tempfile.mkdtemp(prefix="minipack_"))
    in_path = tmp / "input.3mf"
    out_path = tmp / "packed.3mf"
    in_path.write_bytes(data)

    try:
        model = threemf.ThreeMF.load(str(in_path))
    except Exception as e:  # zip/xml errors -> uniform message
        raise NestError(f"could not read 3MF: {e}")

    oid = _pick_source_object(model)
    obj = model.objects[oid]
    # Pack the ORIENTED part (the source build-item transform applied) so the
    # footprint is its true top-down projection and saved geometry stands as in
    # the source; mirrors ``cli.run_nest``.
    t_src = next(
        (it.transform for it in model.build_items if it.object_id == oid), None
    )
    t_src = t_src if t_src is not None else threemf.IDENTITY
    verts_o = threemf.apply_transform(obj.vertices, t_src)
    footprint = [(x, y) for x, y, _z in verts_o]
    (_lx, _ly, min_z), (_hx, _hy, max_z) = threemf.bounding_box(verts_o)
    part_height = max_z - min_z

    spec = (tower or "auto").strip().lower()
    if spec not in ("auto", "off"):
        raise NestError(f'invalid tower value {spec!r}: expected "auto" or "off"')
    reserve = (
        None
        if spec == "off"
        else _auto_tower(
            has_paint=obj.has_paint,
            n_colors=model.paint_color_count() + 1,
            bed_w=bed_w,
            bed_d=bed_d,
            margin=margin,
        )
    )

    result = packing.pack(
        footprint,
        part_height,
        target_dim=target,
        spacing=spacing,
        bed_w=bed_w,
        bed_d=bed_d,
        count=count,
        angle_step_deg=angle_step,
        mode=pack_mode,
        reserve=reserve,
        margin=margin,
    )
    if not result.placements:
        raise NestError(
            f"nothing fits on the bed ({bed_w:g}x{bed_d:g} mm); "
            "try scaling down or a larger bed"
        )

    tz = -min_z * result.scale
    items = [
        threemf.BuildItem(
            oid,
            threemf.compose_affine(
                t_src,
                threemf.compose_transform(result.scale, p.rot_deg, p.x, p.y, tz),
            ),
        )
        for p in result.placements
    ]
    # Surgical save (matches the CLI/webapp default): keep the colour-bearing
    # metadata and rewrite model_settings for the new instances, dropping only
    # stale plate artifacts. With printer="u1" the project is rewritten into a
    # native Snapmaker U1 profile carrying the source's filament colours; with
    # "source" the source profile is kept and only its bed is patched. Stripping
    # all of Metadata/ loses per-object extruder + filament colours (Rayquaza
    # regression), so the surgical save always keeps it.
    model.save(
        str(out_path), items,
        **model.surgical_save_kwargs(bed_w, bed_d, items, printer=printer),
    )

    svg = packing.preview_svg(
        result, footprint, bed_w, bed_d, reserve=reserve, margin=margin
    )
    return {
        "svg": svg,
        "placed": len(items),
        "method": result.method,
        "scale": result.scale,
        "utilization": result.bed_utilization,
        "usable_utilization": result.usable_utilization,
        "warnings": list(result.warnings),
        "reserve": reserve,
        "out_path": str(out_path),
    }


# --------------------------------------------------------------------------- #
# Color-swap analyzer (mirrors ``multipack.cli`` analyze/postprocess semantics)
# --------------------------------------------------------------------------- #


def _decode(data: bytes) -> list[str]:
    """Bytes -> G-code lines, matching the CLI's lenient read."""
    return data.decode("utf-8", errors="replace").splitlines()


def _tool_label(report: gcode.GcodeReport, tool: int) -> str:
    """"T5 (#008080)" when a filament color is known, else "T5". These strings
    go into G-code comments, so hex-only (no ambiguous names, no ANSI); matches
    the plain ``cli._tool_label`` output so injected pause notes are identical."""
    hexv = report.filament_colors.get(tool)
    if hexv:
        return f"T{tool} ({hexv})"
    return f"T{tool}"


def _swap_notes(report: gcode.GcodeReport, plan: gcode.SwapPlan) -> dict[int, str]:
    """One note per pause layer describing every head change (mirrors the CLI)."""
    by_layer: dict[int, list[gcode.Swap]] = defaultdict(list)
    for w in plan.swaps:
        by_layer[w.pause_after_layer].append(w)
    notes: dict[int, str] = {}
    for layer, ws in by_layer.items():
        parts = [
            f"Head {w.head + 1}: remove {_tool_label(report, w.out_tool)}, "
            f"load {_tool_label(report, w.in_tool)} (needed by layer {w.needed_by_layer})"
            for w in sorted(ws, key=lambda w: w.head)
        ]
        notes[layer] = "; ".join(parts)
    return notes


def _tool_info(report: gcode.GcodeReport, tool: int) -> dict:
    """JSON-able chip descriptor: real filament hex + nearest color name."""
    hexv = report.filament_colors.get(tool)
    return {
        "tool": tool,
        "hex": hexv,
        "name": gcode.nearest_color_name(hexv).title() if hexv else "",
    }


def analyze_lines(lines: list[str], max_tools: int = 4) -> dict:
    """Analyze already-decoded G-code lines. Returns a JSON-serializable report:
    stats, the swap plan, and merge options (sets -> sorted lists throughout)."""
    report = gcode.analyze(lines, max_tools=max_tools)
    plan = gcode.plan_swaps(report, max_tools=max_tools)
    options = gcode.suggest_merges(report, max_tools=max_tools)

    colors_used = sorted(report.tool_totals)
    max_on_layer = max((len(l.tools) for l in report.layers), default=0)

    plan_dict = {
        "feasible": plan.feasible,
        "blocking": plan.blocking,
        "initial_loadout": [
            [h, t] for h, t in sorted(plan.initial_loadout.items())
        ],
        "swaps": [
            {
                "head": w.head,
                "out_tool": w.out_tool,
                "in_tool": w.in_tool,
                "pause_after_layer": w.pause_after_layer,
                "needed_by_layer": w.needed_by_layer,
            }
            for w in plan.swaps
        ],
        "pause_layers": list(plan.pause_layers),
        "needs_remap": plan.needs_remap(max_tools),
    }

    merge_options = [
        {
            "merges": [[l, s] for l, s in o.merges],
            "delta_es": [float(de) for de in o.delta_es],
            "shade_phrase": gcode._shade_phrase(max(o.delta_es)),
            "pauses_before": o.pauses_before,
            "pauses_after": o.pauses_after,
            "label": o.label,
        }
        for o in options
    ]

    return {
        "total_layers": report.total_layers,
        "max_colors_on_layer": max_on_layer,
        "colors_used": colors_used,
        "tool_info": {str(t): _tool_info(report, t) for t in colors_used},
        "plan": plan_dict,
        "merge_options": merge_options,
    }


def process_lines(
    lines: list[str],
    merges: list[tuple[int, int]],
    pause_cmd: str = "M600",
    max_tools: int = 4,
) -> tuple[bytes, dict]:
    """Apply ``merges``, inject pauses at the resulting plan's layers, and remap
    tools to physical heads when needed -- exactly as ``cli.cmd_analyze --inject``
    and ``cli.cmd_postprocess`` do. Returns (processed bytes, JSON-able summary)."""
    merges = [tuple(m) for m in merges]
    if merges:
        lines = gcode.apply_merges(lines, merges)

    report = gcode.analyze(lines, max_tools=max_tools)
    plan = gcode.plan_swaps(report, max_tools=max_tools)

    needs_swaps = plan.feasible and bool(plan.swaps)
    needs_remap = plan.feasible and plan.needs_remap(max_tools)
    after = list(plan.pause_layers)
    notes = _swap_notes(report, plan) if needs_swaps else None

    out = gcode.inject_pauses(lines, after, command=pause_cmd, notes=notes)
    if needs_remap:
        out = gcode.remap_tools(out, plan)

    injected = out.count(pause_cmd) - lines.count(pause_cmd)
    placed = sorted({n + 1 for n in after if n + 1 < report.total_layers})
    text = "\n".join(out) + "\n"
    summary = {
        "feasible": plan.feasible,
        "blocking": plan.blocking,
        "merges_applied": [[l, s] for l, s in merges],
        "swaps": len(plan.swaps),
        "pauses": injected,
        "pause_layers": placed,
        "remapped": needs_remap,
    }
    return text.encode("utf-8"), summary


def analyze_gcode(data: bytes, max_tools: int = 4) -> dict:
    """Analyze raw sliced G-code bytes. See :func:`analyze_lines`."""
    return analyze_lines(_decode(data), max_tools=max_tools)


def process_gcode(
    data: bytes,
    merges: list[tuple[int, int]],
    pause_cmd: str = "M600",
    max_tools: int = 4,
) -> tuple[bytes, dict]:
    """Process raw sliced G-code bytes. See :func:`process_lines`."""
    return process_lines(_decode(data), merges, pause_cmd=pause_cmd, max_tools=max_tools)
