"""G-code color-swap analyzer for multi-tool prints.

Parses Orca/Bambu-flavored G-code to build a per-layer picture of which tools
extrude where, detects layers that need more physical tools than available, and
suggests filament-swap pauses at points where a tool retires for good.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable


PAUSE_COMMENT = "; multipack: pause - swap filament"

_Z_RE = re.compile(r";\s*Z\s*:\s*([-+]?\d*\.?\d+)")
_ZH_RE = re.compile(r";\s*Z_HEIGHT\s*:\s*([-+]?\d*\.?\d+)", re.IGNORECASE)
_DIAM_RE = re.compile(r"filament_diameter\s*=\s*([-+]?\d*\.?\d+)")
_TOOL_RE = re.compile(r"^T(\d+)\b")
_FIL_COLOR_RE = re.compile(r"filament_colou?r\s*=\s*(.+)")
_HEX6_RE = re.compile(r"#[0-9A-Fa-f]{6}")
_LEADING_TOOL_RE = re.compile(r"^(\s*)T(\d+)(.*)$")
_TEMP_TOOL_RE = re.compile(r"(?<![A-Za-z])T(\d+)")

# Common filament colors for nearest-name lookup (display only). A name may
# carry several RGB anchors — warm neutrals especially need more than one
# reference point to avoid absurd matches (e.g. warm beige reading as silver).
_COLOR_NAMES: list[tuple[str, tuple[int, int, int]]] = [
    ("black", (0, 0, 0)), ("white", (255, 255, 255)), ("gray", (128, 128, 128)),
    ("silver", (192, 192, 192)), ("red", (255, 0, 0)), ("dark red", (139, 0, 0)),
    ("orange", (255, 165, 0)), ("brown", (139, 69, 19)), ("brown", (133, 94, 66)),
    ("yellow", (255, 255, 0)), ("gold", (255, 215, 0)),
    ("green", (0, 128, 0)), ("dark green", (0, 100, 0)), ("lime", (0, 255, 0)),
    ("olive", (128, 128, 0)), ("teal", (0, 128, 128)), ("cyan", (0, 255, 255)),
    ("sky blue", (135, 206, 235)), ("blue", (0, 0, 255)), ("navy", (0, 0, 128)),
    ("purple", (128, 0, 128)), ("violet", (138, 43, 226)),
    ("magenta", (255, 0, 255)), ("pink", (255, 192, 203)),
    ("beige", (245, 245, 220)), ("beige", (234, 221, 202)), ("beige", (222, 196, 176)),
    ("tan", (210, 180, 140)), ("tan", (222, 184, 135)),
    ("rose", (255, 102, 153)), ("cream", (255, 253, 208)),
    ("mint", (152, 255, 152)), ("lavender", (181, 126, 220)), ("maroon", (128, 0, 0)),
]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int] | None:
    s = hex_color.strip().lstrip("#")
    if len(s) < 6:
        return None
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return None


def _srgb_to_lab(hex_color: str) -> tuple[float, float, float] | None:
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return None

    def lin(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = lin(rgb[0]), lin(rgb[1]), lin(rgb[2])
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047  # D65 white point
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        if t > 216.0 / 24389.0:
            return t ** (1.0 / 3.0)
        return (24389.0 / 27.0 * t + 16.0) / 116.0

    fx, fy, fz = f(x), f(y), f(z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def delta_e(hex_a: str, hex_b: str) -> float:
    """CIE76 color difference between two ``#RRGGBB`` strings."""
    la, lb = _srgb_to_lab(hex_a), _srgb_to_lab(hex_b)
    if la is None or lb is None:
        return math.inf
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(la, lb)))


def _shade_phrase(de: float) -> str:
    if de < 12:
        return "nearly identical shades"
    if de < 25:
        return "similar shades"
    return "noticeably different shades"


def nearest_color_name(hex_color: str) -> str:
    """Nearest common color name for a ``#RRGGBB`` string.

    Uses the "redmean" weighted RGB distance, which tracks perception far
    better than plain Euclidean RGB for warm/neutral tones.
    """
    rgb = _hex_to_rgb(hex_color)
    if rgb is None:
        return hex_color
    best: str | None = None
    best_d: float | None = None
    for name, (r, g, b) in _COLOR_NAMES:
        rbar = (rgb[0] + r) / 2.0
        dr, dg, db = rgb[0] - r, rgb[1] - g, rgb[2] - b
        d = (
            (2.0 + rbar / 256.0) * dr * dr
            + 4.0 * dg * dg
            + (2.0 + (255.0 - rbar) / 256.0) * db * db
        )
        if best_d is None or d < best_d:
            best_d, best = d, name
    return best or hex_color


@dataclass
class LayerInfo:
    index: int
    z: float | None
    tools: set[int]
    extrusion_by_tool: dict[int, float]


@dataclass
class Conflict:
    layer: int
    tools: set[int]


@dataclass
class PauseSuggestion:
    after_layer: int
    freed_tool: int
    reason: str


@dataclass
class Swap:
    head: int
    out_tool: int
    in_tool: int
    pause_after_layer: int
    needed_by_layer: int


@dataclass
class SwapPlan:
    feasible: bool
    blocking: str | None
    initial_loadout: dict[int, int]
    swaps: list[Swap]
    head_timeline: list[tuple[int, int, int, int]]
    tool_to_head: list[tuple[int, int, int, int]]
    pause_layers: list[int]

    def needs_remap(self, max_tools: int) -> bool:
        """True when the G-code contains tool numbers a max_tools-head machine
        cannot execute directly (any swap, or a logical tool >= max_tools)."""
        if self.swaps:
            return True
        return any(t >= max_tools for t, _h, _s, _e in self.tool_to_head)


@dataclass
class MergeOption:
    merges: list[tuple[int, int]]  # (loser, survivor)
    delta_es: list[float]
    pauses_before: int
    pauses_after: int
    filament_saved_swaps: int
    label: str


@dataclass
class GcodeReport:
    layers: list[LayerInfo]
    first_use: dict[int, int]
    last_use: dict[int, int]
    conflicts: list[Conflict]
    pause_suggestions: list[PauseSuggestion]
    elimination_hints: list[str]
    total_layers: int
    tool_totals: dict[int, float]
    filament_diameter: float | None
    filament_colors: dict[int, str] = field(default_factory=dict)
    segments: dict[int, list[tuple[int, int]]] = field(default_factory=dict)

    def volume_mm3(self, tool: int) -> float | None:
        """Extruded volume in mm^3 for a tool, or None if diameter is unknown."""
        if self.filament_diameter is None:
            return None
        radius = self.filament_diameter / 2.0
        return math.pi * radius * radius * self.tool_totals.get(tool, 0.0)


@dataclass
class _Layer:
    index: int
    z: float | None = None
    extrusion: dict[int, float] = field(default_factory=dict)


def _is_boundary(line: str) -> bool:
    s = line.strip()
    return (
        s.startswith(";LAYER_CHANGE")
        or s.startswith("; CHANGE_LAYER")
        or s.startswith(";LAYER:")
    )


def _parse_z(comment: str) -> float | None:
    m = _Z_RE.match(comment)
    if m:
        return float(m.group(1))
    m = _ZH_RE.match(comment)
    if m:
        return float(m.group(1))
    return None


def _param(line: str, letter: str) -> float | None:
    m = re.search(rf"(?:^|\s){letter}([-+]?\d*\.?\d+)", line)
    return float(m.group(1)) if m else None


def _scan(lines: list[str]) -> tuple[list[_Layer], list[int | None], float | None]:
    """Return (layers, boundary_line_index_per_layer, filament_diameter)."""
    if any(_is_boundary(l) for l in lines):
        return _scan_comment(lines)
    return _scan_zfallback(lines)


def _scan_comment(
    lines: list[str],
) -> tuple[list[_Layer], list[int | None], float | None]:
    layers: list[_Layer] = []
    boundary_lines: list[int | None] = []
    current: _Layer | None = None
    tool = 0
    absolute = True
    last_e = 0.0
    diameter: float | None = None

    def add_extrusion(delta: float) -> None:
        nonlocal current
        if delta <= 0:
            return
        if current is None:
            current = _Layer(index=0)
            layers.append(current)
            boundary_lines.append(None)
        current.extrusion[tool] = current.extrusion.get(tool, 0.0) + delta

    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s:
            continue
        if diameter is None and "filament_diameter" in s:
            m = _DIAM_RE.search(s)
            if m:
                diameter = float(m.group(1))
        if _is_boundary(raw):
            current = _Layer(index=len(layers))
            layers.append(current)
            boundary_lines.append(i)
            continue
        if s.startswith(";"):
            if current is not None and current.z is None:
                z = _parse_z(s)
                if z is not None:
                    current.z = z
            continue
        code = s.split(";", 1)[0].strip()  # inline comments may contain E/Z text
        if not code:
            continue
        mt = _TOOL_RE.match(code)
        if mt:
            n = int(mt.group(1))
            if n != 255 and n < 1000:
                tool = n
            continue
        if code.startswith("M82"):
            absolute = True
            continue
        if code.startswith("M83"):
            absolute = False
            continue
        if code.startswith("G92"):
            e = _param(code, "E")
            if e is not None:
                last_e = e
            continue
        head = code.split(" ", 1)[0]
        if head in ("G0", "G1", "G2", "G3"):
            e = _param(code, "E")
            if e is not None:
                if absolute:
                    add_extrusion(e - last_e)
                    last_e = e
                else:
                    add_extrusion(e)
            continue

    return layers, boundary_lines, diameter


def _scan_zfallback(
    lines: list[str],
) -> tuple[list[_Layer], list[int | None], float | None]:
    layers: list[_Layer] = []
    boundary_lines: list[int | None] = []
    current: _Layer | None = None
    tool = 0
    absolute = True
    last_e = 0.0
    cur_z: float | None = None  # tracked across moves: Z often changes on travel lines
    diameter: float | None = None
    eps = 1e-9

    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if diameter is None and "filament_diameter" in s:
            m = _DIAM_RE.search(s)
            if m:
                diameter = float(m.group(1))
        if s.startswith(";"):
            continue
        code = s.split(";", 1)[0].strip()
        if not code:
            continue
        mt = _TOOL_RE.match(code)
        if mt:
            n = int(mt.group(1))
            if n != 255 and n < 1000:
                tool = n
            continue
        if code.startswith("M82"):
            absolute = True
            continue
        if code.startswith("M83"):
            absolute = False
            continue
        if code.startswith("G92"):
            e = _param(code, "E")
            if e is not None:
                last_e = e
            continue
        head = code.split(" ", 1)[0]
        if head in ("G0", "G1", "G2", "G3"):
            z = _param(code, "Z")
            if z is not None:
                cur_z = z
            e = _param(code, "E")
            delta = 0.0
            if e is not None:
                if absolute:
                    delta = e - last_e
                    last_e = e
                else:
                    delta = e
            if delta > 0:
                if current is None:
                    current = _Layer(index=0, z=cur_z)
                    layers.append(current)
                    boundary_lines.append(None)
                elif (
                    cur_z is not None
                    and current.z is not None
                    and cur_z > current.z + eps
                ):
                    current = _Layer(index=len(layers), z=cur_z)
                    layers.append(current)
                    boundary_lines.append(None)
                elif current.z is None and cur_z is not None:
                    current.z = cur_z
                current.extrusion[tool] = current.extrusion.get(tool, 0.0) + delta

    return layers, boundary_lines, diameter


def _parse_filament_colors(lines: list[str]) -> dict[int, str]:
    """Tool index -> ``#RRGGBB`` from an Orca/Bambu config-block comment."""
    for raw in lines:
        m = _FIL_COLOR_RE.search(raw)
        if m:
            hexes = _HEX6_RE.findall(m.group(1))
            if hexes:
                return {i: h.upper() for i, h in enumerate(hexes)}
    return {}


def _compute_segments(
    layer_infos: list[LayerInfo], min_gap_layers: int
) -> dict[int, list[tuple[int, int]]]:
    """Per tool, maximal contiguous extruding runs, merging gaps < min_gap."""
    tool_layers: dict[int, list[int]] = defaultdict(list)
    for l in layer_infos:
        for t in l.tools:
            tool_layers[t].append(l.index)

    segments: dict[int, list[tuple[int, int]]] = {}
    for t in sorted(tool_layers):
        idxs = sorted(tool_layers[t])
        runs: list[tuple[int, int]] = []
        start = prev = idxs[0]
        for i in idxs[1:]:
            if i == prev + 1:
                prev = i
            else:
                runs.append((start, prev))
                start = prev = i
        runs.append((start, prev))

        merged = [runs[0]]
        for s, e in runs[1:]:
            ps, pe = merged[-1]
            if s - pe - 1 < min_gap_layers:
                merged[-1] = (ps, e)
            else:
                merged.append((s, e))
        segments[t] = merged
    return segments


def analyze(
    lines: Iterable[str], max_tools: int = 4, min_gap_layers: int = 15
) -> GcodeReport:
    lines = list(lines)
    layers, _boundary_lines, diameter = _scan(lines)

    first_use: dict[int, int] = {}
    last_use: dict[int, int] = {}
    tool_totals: dict[int, float] = defaultdict(float)
    for layer in layers:
        for t, v in layer.extrusion.items():
            tool_totals[t] += v
            first_use.setdefault(t, layer.index)
            last_use[t] = layer.index

    layer_infos = [
        LayerInfo(
            index=l.index,
            z=l.z,
            tools=set(l.extrusion.keys()),
            extrusion_by_tool=dict(l.extrusion),
        )
        for l in layers
    ]

    conflicts = [
        Conflict(layer=l.index, tools=set(l.extrusion.keys()))
        for l in layers
        if len(l.extrusion) > max_tools
    ]

    last_index = len(layers) - 1
    pause_suggestions: list[PauseSuggestion] = []
    for t, li in last_use.items():
        if li < last_index:
            pause_suggestions.append(
                PauseSuggestion(
                    after_layer=li,
                    freed_tool=t,
                    reason=f"T{t} finishes at layer {li}; head free for a new color",
                )
            )
    pause_suggestions.sort(key=lambda p: (p.after_layer, p.freed_tool))

    elimination_hints: list[str] = []
    if conflicts:
        for c in conflicts:
            candidate = min(c.tools, key=lambda t: tool_totals.get(t, 0.0))
            elimination_hints.append(
                f"Layer {c.layer}: eliminate T{candidate} (lowest total extrusion) "
                f"or reduce the number of model instances"
            )

    return GcodeReport(
        layers=layer_infos,
        first_use=first_use,
        last_use=last_use,
        conflicts=conflicts,
        pause_suggestions=pause_suggestions,
        elimination_hints=elimination_hints,
        total_layers=len(layers),
        tool_totals=dict(tool_totals),
        filament_diameter=diameter,
        filament_colors=_parse_filament_colors(lines),
        segments=_compute_segments(layer_infos, min_gap_layers),
    )


def plan_swaps(report: GcodeReport, max_tools: int = 4) -> SwapPlan:
    """Assign each usage segment to a physical head, scheduling filament swaps.

    Segments are treated as intervals needing a head; a deterministic greedy
    interval partitioning (stability -> tightest fit -> new head) yields the
    initial loadout, per-head timeline, tool->head map, and swap list.
    """
    segs: list[tuple[int, int, int]] = []  # (start, end, tool)
    for tool, runs in report.segments.items():
        for s, e in runs:
            segs.append((s, e, tool))
    distinct = sorted(report.segments.keys())

    empty = SwapPlan(
        feasible=True, blocking=None, initial_loadout={}, swaps=[],
        head_timeline=[], tool_to_head=[], pause_layers=[],
    )
    if not segs:
        return empty

    # Feasibility: no layer may need more concurrent segments than heads.
    total = report.total_layers
    delta = [0] * (total + 1)
    for s, e, _t in segs:
        delta[s] += 1
        if e + 1 <= total:
            delta[e + 1] -= 1
    active = 0
    for layer in range(total):
        active += delta[layer]
        if active > max_tools:
            tools = sorted(t for s, e, t in segs if s <= layer <= e)
            msg = (
                f"layer {layer} needs {active} colors loaded at once "
                f"(> max {max_tools} heads): tools {tools}. Reduce distinct "
                f"colors or increase --max-tools."
            )
            return SwapPlan(
                feasible=False, blocking=msg, initial_loadout={}, swaps=[],
                head_timeline=[], tool_to_head=[], pause_layers=[],
            )

    initial: dict[int, int] = {}
    swaps: list[Swap] = []
    head_timeline: list[tuple[int, int, int, int]] = []
    tool_to_head: list[tuple[int, int, int, int]] = []

    # <= max_tools distinct tools: give each its own head, no swaps.
    if len(distinct) <= max_tools:
        for head, tool in enumerate(distinct):
            runs = report.segments[tool]
            start, end = runs[0][0], runs[-1][1]
            initial[head] = tool
            head_timeline.append((head, tool, start, end))
            tool_to_head.append((tool, head, start, end))
        return SwapPlan(
            feasible=True, blocking=None, initial_loadout=initial, swaps=[],
            head_timeline=head_timeline, tool_to_head=tool_to_head,
            pause_layers=[],
        )

    head_end: dict[int, int] = {}    # head -> layer it frees after
    head_tool: dict[int, int] = {}   # head -> tool currently on it
    tool_prev_head: dict[int, int] = {}
    used = 0

    for s, e, tool in sorted(segs, key=lambda x: (x[0], x[2])):
        prev = tool_prev_head.get(tool)
        if prev is not None and head_end[prev] < s:
            chosen = prev            # stability: reuse this tool's own head
        else:
            best: int | None = None  # tightest fit among free used heads
            for h in range(used):
                if head_end[h] < s and (best is None or head_end[h] > head_end[best]):
                    best = h
            if best is not None:
                chosen = best
            elif used < max_tools:
                chosen = used
                used += 1
            else:  # feasibility guarantees this never happens
                chosen = min(range(used), key=lambda h: head_end[h])

        if chosen not in head_tool:
            initial[chosen] = tool
        elif head_tool[chosen] != tool:
            swaps.append(
                Swap(
                    head=chosen,
                    out_tool=head_tool[chosen],
                    in_tool=tool,
                    pause_after_layer=head_end[chosen],
                    needed_by_layer=s,
                )
            )
        head_end[chosen] = e
        head_tool[chosen] = tool
        tool_prev_head[tool] = chosen
        head_timeline.append((chosen, tool, s, e))
        tool_to_head.append((tool, chosen, s, e))

    swaps.sort(key=lambda w: (w.pause_after_layer, w.head))
    head_timeline.sort(key=lambda x: (x[0], x[2]))
    tool_to_head.sort(key=lambda x: (x[0], x[2]))
    pause_layers = sorted({w.pause_after_layer for w in swaps})
    return SwapPlan(
        feasible=True, blocking=None, initial_loadout=initial, swaps=swaps,
        head_timeline=head_timeline, tool_to_head=tool_to_head,
        pause_layers=pause_layers,
    )


def _merged_plan(
    report: GcodeReport, merges: list[tuple[int, int]], max_tools: int
) -> SwapPlan:
    """Plan for the report with each loser tool's extrusion given to its survivor."""
    mapping = {loser: survivor for loser, survivor in merges}
    layers: list[LayerInfo] = []
    for l in report.layers:
        ext: dict[int, float] = {}
        for t, v in l.extrusion_by_tool.items():
            tt = mapping.get(t, t)
            ext[tt] = ext.get(tt, 0.0) + v
        layers.append(
            LayerInfo(index=l.index, z=l.z, tools=set(ext), extrusion_by_tool=ext)
        )
    stub = GcodeReport(
        layers=layers, first_use={}, last_use={}, conflicts=[],
        pause_suggestions=[], elimination_hints=[],
        total_layers=report.total_layers, tool_totals={},
        filament_diameter=None, filament_colors=report.filament_colors,
        segments=_compute_segments(layers, 15),
    )
    return plan_swaps(stub, max_tools=max_tools)


def _merge_label(
    report: GcodeReport,
    merges: list[tuple[int, int]],
    delta_es: list[float],
    base_feasible: bool,
    pauses_before: int,
    pauses_after: int,
) -> str:
    def tool_desc(t: int) -> str:
        # Hex is the identity; names are ambiguous (two hexes can share a name).
        hexv = report.filament_colors.get(t, "")
        return f"T{t} ({hexv})" if hexv else f"T{t}"

    parts = [
        f"merge {tool_desc(l)} into {tool_desc(s)}" for l, s in merges
    ]
    phrase = _shade_phrase(max(delta_es))
    before = f"{pauses_before} pauses" if base_feasible else "infeasible"
    after = f"{pauses_after} pause{'s' if pauses_after != 1 else ''}"
    return f"{' + '.join(parts)} — {phrase}; {before} -> {after}"


def suggest_merges(report: GcodeReport, max_tools: int = 4) -> list[MergeOption]:
    """Merge options (combine visually close filament colors) that cut pauses.

    Empty when the base plan is already pause-free, or when no tool pair with
    known colors lands within delta-E 40. Each option is a single pair, plus one
    greedy multi-pair set (delta-E ascending, non-overlapping) when it merges
    more than one pair. Survivor defaults to the larger-volume tool.
    """
    base = plan_swaps(report, max_tools=max_tools)
    if base.feasible and not base.swaps:
        return []

    colors = report.filament_colors
    tools = sorted(t for t in report.tool_totals if t in colors)
    pairs: list[tuple[float, int, int]] = []
    for i, a in enumerate(tools):
        for b in tools[i + 1:]:
            de = delta_e(colors[a], colors[b])
            if de <= 40:
                pairs.append((de, a, b))
    if not pairs:
        return []
    pairs.sort()

    def directed(a: int, b: int) -> tuple[int, int]:
        """(loser, survivor): survivor = larger total extrusion, ties -> lower."""
        va, vb = report.tool_totals.get(a, 0.0), report.tool_totals.get(b, 0.0)
        if va > vb or (va == vb and a < b):
            return b, a
        return a, b

    candidate_sets: list[list[tuple[float, int, int]]] = [[p] for p in pairs]
    greedy: list[tuple[float, int, int]] = []
    taken: set[int] = set()
    distinct = len(report.segments)
    for de, a, b in pairs:
        if distinct - len(greedy) <= max_tools:
            break
        if a in taken or b in taken:
            continue
        greedy.append((de, a, b))
        taken.update((a, b))
    if len(greedy) > 1:
        candidate_sets.append(greedy)

    pauses_before = len(base.pause_layers)
    options: list[MergeOption] = []
    for cand in candidate_sets:
        merges = [directed(a, b) for _de, a, b in cand]
        plan = _merged_plan(report, merges, max_tools)
        if not plan.feasible:
            continue
        pauses_after = len(plan.pause_layers)
        if base.feasible and pauses_after >= pauses_before:
            continue
        delta_es = [de for de, _a, _b in cand]
        options.append(
            MergeOption(
                merges=merges,
                delta_es=delta_es,
                pauses_before=pauses_before,
                pauses_after=pauses_after,
                filament_saved_swaps=max(0, len(base.swaps) - len(plan.swaps)),
                label=_merge_label(
                    report, merges, delta_es, base.feasible,
                    pauses_before, pauses_after,
                ),
            )
        )

    options.sort(key=lambda o: (o.pauses_after, max(o.delta_es), len(o.merges)))
    return options[:5]


def apply_merges(
    lines: Iterable[str], merges: list[tuple[int, int]]
) -> list[str]:
    """Rewrite every loser-tool reference to its survivor, whole file.

    Chains resolve transitively ((2,0) then (0,1) sends T2 to T1). Rewrites
    leading ``T<n>`` commands and ``T<n>`` params on M104/M109; composable with
    ``remap_tools`` (merge first, then plan + remap the merged file).
    """
    lines = list(lines)
    mapping = {loser: survivor for loser, survivor in merges}

    def resolve(t: int) -> int:
        seen: set[int] = set()
        while t in mapping and t not in seen:
            seen.add(t)
            t = mapping[t]
        return t

    resolved = {loser: resolve(loser) for loser in mapping}

    out: list[str] = []
    for raw in lines:
        m = _LEADING_TOOL_RE.match(raw)
        if m:
            n = int(m.group(2))
            if n != 255 and n < 1000 and n in resolved:
                out.append(f"{m.group(1)}T{resolved[n]}{m.group(3)}")
                continue
            out.append(raw)
            continue

        code = raw.lstrip()
        if code.startswith(("M104", "M109")):
            def repl(mo: "re.Match[str]") -> str:
                n = int(mo.group(1))
                if n == 255 or n >= 1000 or n not in resolved:
                    return mo.group(0)
                return f"T{resolved[n]}"

            out.append(_TEMP_TOOL_RE.sub(repl, raw))
            continue

        out.append(raw)
    return out


def remap_tools(lines: Iterable[str], plan: SwapPlan) -> list[str]:
    """Rewrite tool references so output uses only physical heads 0..N-1.

    Layer-aware: a tool's mapping between/after its segments follows its next
    (or last) segment; before its first segment follows its first. Rewrites
    leading ``T<n>`` commands and ``T<n>`` params on M104/M109. Non-plan tools
    and every other byte are preserved.
    """
    lines = list(lines)
    if not plan.feasible:
        return lines

    # tool -> segments sorted by end: (end, head)
    by_tool: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for tool, head, start, end in plan.tool_to_head:
        by_tool[tool].append((end, head))
    for tool in by_tool:
        by_tool[tool].sort()

    def mapped(tool: int, layer: int) -> int | None:
        segs = by_tool.get(tool)
        if not segs:
            return None
        for end, head in segs:
            if end >= layer:
                return head
        return segs[-1][1]

    out: list[str] = []
    current_layer = -1
    for raw in lines:
        if _is_boundary(raw):
            current_layer += 1
            out.append(raw)
            continue
        layer = current_layer if current_layer >= 0 else 0

        m = _LEADING_TOOL_RE.match(raw)
        if m:
            n = int(m.group(2))
            if n != 255 and n < 1000:
                head = mapped(n, layer)
                if head is not None:
                    out.append(f"{m.group(1)}T{head}{m.group(3)}")
                    continue
            out.append(raw)
            continue

        code = raw.lstrip()
        if code.startswith(("M104", "M109")):
            def repl(mo: "re.Match[str]") -> str:
                n = int(mo.group(1))
                if n == 255 or n >= 1000:
                    return mo.group(0)
                head = mapped(n, layer)
                return f"T{head}" if head is not None else mo.group(0)

            out.append(_TEMP_TOOL_RE.sub(repl, raw))
            continue

        out.append(raw)
    return out


def inject_pauses(
    lines: Iterable[str],
    after_layers: list[int],
    command: str = "M600",
    notes: dict[int, str] | None = None,
) -> list[str]:
    """Insert a pause command at the boundary that starts each layer N+1.

    Idempotent: an already-present command+comment pair is not duplicated.
    Pausing after the final layer is a no-op.
    """
    lines = list(lines)
    layers, boundary_lines, _ = _scan(lines)
    n_layers = len(layers)
    notes = notes or {}

    inserts: dict[int, tuple[str, str | None]] = {}
    for n in after_layers:
        target = n + 1
        if target >= n_layers:
            continue
        bl = boundary_lines[target]
        if bl is None:
            continue
        inserts.setdefault(bl, (command, notes.get(n)))

    out: list[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        if i in inserts:
            cmd, note = inserts[i]
            nxt1 = lines[i + 1].strip() if i + 1 < len(lines) else None
            nxt2 = lines[i + 2].strip() if i + 2 < len(lines) else None
            if nxt1 == cmd and nxt2 == PAUSE_COMMENT:
                continue
            out.append(cmd)
            out.append(PAUSE_COMMENT)
            if note:
                out.append(f"; multipack: {note}")
    return out
