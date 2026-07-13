"""Rotation-aware 2D nesting engine (pure stdlib).

The packer arranges congruent copies of a single part's XY footprint on a
rectangular bed, choosing a per-instance rotation to nest interlocking shapes
tighter than a no-rotation layout.

Placement -> 3MF transform convention
-------------------------------------
A ``Placement(x, y, rot_deg, scale)`` describes a rigid placement of the
*source* part. Points are transformed as::

    final_xy = rotate(scale * original_xy, rot_deg) + (x, y)

i.e. **scale first, then rotate about the origin (0, 0), then translate by
(x, y)**. ``x, y`` is therefore the post-rotation translation of the part's
origin, not its centroid. This matches ``threemf.compose_transform`` exactly:

    Placement(x, y, rot_deg, scale)  ==  compose_transform(scale, rot_deg, x, y, tz)

where ``compose_transform`` builds the 3MF row-major 4x3 item transform
(uniform scale + rotation about Z + translation). The CLI phase wires the two
together with no coordinate fixups.

Spacing
-------
Parts end up at least ``spacing`` apart edge-to-edge and at least ``spacing/2``
from the bed edges. This is enforced by inflating each convex hull outward by
``spacing/2`` (exact convex edge-offset: every edge line is pushed out by
``spacing/2`` along its outward normal and adjacent offset lines re-intersected;
corners become sharp, which is slightly conservative vs. a rounded offset).
Non-overlapping inflated hulls therefore keep the real hulls >= ``spacing``
apart, and an inflated hull inside the bed keeps the real hull >= ``spacing/2``
from the edges.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

_EPS = 1e-9
_GRID_STEP = 5.0

# Bitmap (v2) packing: raster cell size (mm) and greedy scan step (in cells).
# 0.5 mm (vs the 1.0 mm sketched in the design) noticeably improves silhouette
# fidelity and interlock quality -- on the 439k-vertex benchmark it lifts the
# placed count from 42 (== hull) to 50 while an auto run still finishes in ~4 s,
# far under the 60 s budget. Documented deviation.
CELL = 0.5
GREEDY_STEP = 2

Point = tuple[float, float]


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class Placement:
    x: float
    y: float
    rot_deg: float
    scale: float


@dataclass
class PackResult:
    placements: list[Placement] = field(default_factory=list)
    scale: float = 1.0
    fits_requested: bool = True
    bed_utilization: float = 0.0
    warnings: list[str] = field(default_factory=list)
    method: str = "hull"
    # utilization of the packable region (bed minus edge margin and tower)
    usable_utilization: float = 0.0


# --------------------------------------------------------------------------- #
# Geometry primitives
# --------------------------------------------------------------------------- #


def convex_hull(points: list[Point]) -> list[Point]:
    """Convex hull via Andrew's monotone chain.

    Returns hull vertices CCW with no duplicate closing point. Collinear points
    are dropped. Degenerate inputs (< 3 unique points) return the unique points.
    """
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) < 3:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _polygon_area(poly: list[Point]) -> float:
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def _bbox(poly: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def inflate_hull(hull: list[Point], r: float) -> list[Point]:
    """Offset a CCW convex polygon outward by ``r`` (exact edge-offset)."""
    n = len(hull)
    if r <= 0 or n < 3:
        return list(hull)
    lines: list[tuple[float, float, float]] = []  # nx*x + ny*y = c
    for i in range(n):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < _EPS:
            continue
        nx, ny = dy / length, -dx / length  # outward normal for CCW winding
        lines.append((nx, ny, nx * x1 + ny * y1 + r))
    m = len(lines)
    out: list[Point] = []
    for i in range(m):
        a0, a1, ac = lines[i - 1]
        b0, b1, bc = lines[i]
        det = a0 * b1 - a1 * b0
        if abs(det) < 1e-12:
            # near-collinear edges: fall back to averaged-normal vertex offset
            vx, vy = hull[i]
            nx, ny = (a0 + b0), (a1 + b1)
            nlen = math.hypot(nx, ny) or 1.0
            out.append((vx + r * nx / nlen, vy + r * ny / nlen))
            continue
        x = (ac * b1 - a1 * bc) / det
        y = (a0 * bc - ac * b0) / det
        out.append((x, y))
    return out


_MAX_HULL_VERTS = 20


def simplify_hull(hull: list[Point], max_verts: int = _MAX_HULL_VERTS) -> list[Point]:
    """Circumscribe a convex hull with at most ``max_verts`` vertices.

    Intersects support lines tangent to the hull in ``max_verts`` evenly spaced
    directions. The result always CONTAINS the input hull (slightly larger, so
    spacing guarantees are preserved) and caps SAT cost for organic meshes whose
    exact hulls can have hundreds of vertices.
    """
    if len(hull) <= max_verts or max_verts < 3:
        return list(hull)
    k = max_verts
    lines: list[tuple[float, float, float]] = []
    for i in range(k):
        th = 2.0 * math.pi * i / k
        nx, ny = math.cos(th), math.sin(th)
        lines.append((nx, ny, max(px * nx + py * ny for px, py in hull)))
    pts: list[Point] = []
    for i in range(k):
        a0, a1, ac = lines[i]
        b0, b1, bc = lines[(i + 1) % k]
        det = a0 * b1 - a1 * b0  # sin(2*pi/k) != 0 for adjacent directions
        pts.append(((ac * b1 - a1 * bc) / det, (a0 * bc - ac * b0) / det))
    cleaned = convex_hull(pts)
    return cleaned if len(cleaned) >= 3 else list(hull)


def _project(poly: list[Point], ax: float, ay: float) -> tuple[float, float]:
    vals = [p[0] * ax + p[1] * ay for p in poly]
    return min(vals), max(vals)


def polygons_overlap(a: list[Point], b: list[Point]) -> bool:
    """SAT overlap test for two convex polygons.

    Touching within ``1e-9`` counts as non-overlapping.
    """
    for poly in (a, b):
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            ax, ay = -(y2 - y1), (x2 - x1)  # edge normal
            length = math.hypot(ax, ay)
            if length < _EPS:
                continue
            ax, ay = ax / length, ay / length
            min_a, max_a = _project(a, ax, ay)
            min_b, max_b = _project(b, ax, ay)
            if max_a <= min_b + _EPS or max_b <= min_a + _EPS:
                return False
    return True


def _transform(points: list[Point], scale: float, rot_deg: float,
               tx: float, ty: float) -> list[Point]:
    theta = math.radians(rot_deg)
    c, s = math.cos(theta), math.sin(theta)
    out: list[Point] = []
    for x, y in points:
        sx, sy = x * scale, y * scale
        out.append((c * sx - s * sy + tx, s * sx + c * sy + ty))
    return out


def placed_polygon(footprint_xy: list[Point], placement: Placement) -> list[Point]:
    """Convex hull of the source footprint after applying ``placement``."""
    hull = convex_hull(footprint_xy)
    return _transform(hull, placement.scale, placement.rot_deg,
                      placement.x, placement.y)


def polygon_distance(a: list[Point], b: list[Point]) -> float:
    """Minimum edge-to-edge distance between two non-overlapping convex polygons.

    Returns 0.0 if they overlap or touch.
    """
    if polygons_overlap(a, b):
        return 0.0
    best = math.inf
    for poly, other in ((a, b), (b, a)):
        n = len(poly)
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            for q in other:
                best = min(best, _point_segment_dist(q, p1, p2))
    return best


def _point_segment_dist(p: Point, a: Point, b: Point) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom < _EPS:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / denom
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


# --------------------------------------------------------------------------- #
# Packer
# --------------------------------------------------------------------------- #


def _angles(angle_step_deg: float) -> list[float]:
    if angle_step_deg <= 0 or angle_step_deg >= 360:
        return [0.0]
    out: list[float] = []
    a = 0.0
    while a < 360.0 - _EPS:
        out.append(a)
        a += angle_step_deg
    return out


def _scale_for(hull0: list[Point], part_height: float,
               target_dim: float | None) -> float:
    bx0, by0, bx1, by1 = _bbox(hull0)
    longest = max(bx1 - bx0, by1 - by0, part_height)
    if target_dim is None or longest <= _EPS:
        return 1.0
    return target_dim / longest


def pack(
    footprint_xy: list[Point],
    part_height: float,
    target_dim: float | None = 50.0,
    spacing: float = 2.0,
    bed_w: float = 270.0,
    bed_d: float = 270.0,
    count: int | None = None,
    angle_step_deg: float = 15.0,
    mode: str = "auto",
    reserve: tuple[float, float, float, float] | None = None,
    margin: float = 0.0,
) -> PackResult:
    """Rotation-aware packing of a single part's footprint.

    ``mode`` selects the strategy:

    * ``"hull"`` -- convex-hull greedy (v1, exact original behaviour).
    * ``"bitmap"`` -- v2 greedy on true raster silhouettes (concave interlock).
    * ``"lattice"`` -- v2 alternating-180 pair lattice, then greedy fill.
    * ``"auto"`` -- if the footprint rasters to a faithful silhouette, run both
      bitmap and lattice and keep whichever places more (ties -> lattice);
      otherwise fall back to hull.

    ``reserve`` is an optional ``(x, y, w, d)`` mm rectangle (e.g. a prime
    tower) kept clear of parts, in addition to spacing, in REAL bed coordinates.

    ``margin`` keeps every part at least ``margin`` mm from every bed edge (e.g.
    Snapmaker U1 spiral-lift clearance). Parts already sit ``spacing/2`` from the
    packing-area edge, so the usable area is inset by
    ``max(0, margin - spacing/2)`` per side and every placement is shifted back
    out by that inset. Afterwards the whole layout is recentred on the bed.
    """
    inset = max(0.0, margin - spacing / 2.0)
    pack_w = bed_w - 2.0 * inset
    pack_d = bed_d - 2.0 * inset
    reserve_in: tuple[float, float, float, float] | None = None
    if reserve is not None:
        rx, ry, rw, rd = reserve
        reserve_in = (rx - inset, ry - inset, rw, rd)

    hull0 = convex_hull(footprint_xy)
    use_hull = mode == "hull" or len(hull0) < 3
    scale = base_area = None
    scaled_pts: list[Point] = []
    if not use_hull:
        scale = _scale_for(hull0, part_height, target_dim)
        scaled_pts = [(x * scale, y * scale) for x, y in footprint_xy]
        base_area = _polygon_area([(x * scale, y * scale) for x, y in hull0])
        from . import bitmap
        if mode == "auto" and not bitmap.dense_enough(scaled_pts, CELL, base_area):
            use_hull = True

    if use_hull:
        result = _pack_hull(footprint_xy, part_height, target_dim, spacing,
                            pack_w, pack_d, count, angle_step_deg, reserve_in,
                            bed_w, bed_d)
        _center_hull(result, footprint_xy, spacing, pack_w, pack_d, reserve_in)
    else:
        from . import bitmap
        angles = _bitmap_angles(angle_step_deg)
        masks = bitmap.make_masks(scaled_pts, angles, spacing, CELL, base_area)
        if mode == "bitmap":
            placements = _pack_bitmap(masks, angles, pack_w, pack_d, count,
                                      scale, reserve_in)
            method = "bitmap"
        elif mode == "lattice":
            placements = _pack_lattice(masks, angles, pack_w, pack_d, count,
                                       scale, angle_step_deg, reserve_in)
            method = "lattice"
        else:  # auto + dense
            bmp = _pack_bitmap(masks, angles, pack_w, pack_d, count, scale,
                               reserve_in)
            lat = _pack_lattice(masks, angles, pack_w, pack_d, count, scale,
                                angle_step_deg, reserve_in)
            if len(lat) >= len(bmp):
                placements, method = lat, "lattice"
            else:
                placements, method = bmp, "bitmap"
        result = _finalize_v2(placements, scale, base_area, bed_w, bed_d,
                              count, method)
        _center_v2(result, masks, pack_w, pack_d, reserve_in)

    if inset:
        for p in result.placements:
            p.x += inset
            p.y += inset

    # "Bed used" (bed_utilization) divides by the whole bed; this divides by
    # what was actually packable: bed minus the edge margin and the tower.
    usable = (bed_w - 2.0 * margin) * (bed_d - 2.0 * margin)
    if reserve is not None:
        usable -= max(0.0, reserve[2]) * max(0.0, reserve[3])
    part_area = _polygon_area(hull0) * result.scale * result.scale
    if usable > _EPS:
        result.usable_utilization = min(
            1.0, len(result.placements) * part_area / usable
        )
    return result


def _pack_hull(
    footprint_xy: list[Point],
    part_height: float,
    target_dim: float | None,
    spacing: float,
    pack_w: float,
    pack_d: float,
    count: int | None,
    angle_step_deg: float,
    reserve: tuple[float, float, float, float] | None = None,
    bed_w: float | None = None,
    bed_d: float | None = None,
) -> PackResult:
    """Greedy rotation-aware bottom-left packing on inflated convex hulls.

    Geometry is packed into ``pack_w x pack_d`` (the margin-inset usable area);
    ``bed_w/bed_d`` are the real bed dimensions used only for utilization and
    warning messages (default to the packing area)."""
    if bed_w is None:
        bed_w = pack_w
    if bed_d is None:
        bed_d = pack_d
    warnings: list[str] = []
    hull0 = convex_hull(footprint_xy)
    if len(hull0) < 3:
        return PackResult(scale=1.0, fits_requested=count in (None, 0),
                          warnings=["footprint has no 2D area"])

    scale = _scale_for(hull0, part_height, target_dim)

    base_hull = [(x * scale, y * scale) for x, y in hull0]
    base_area = _polygon_area(base_hull)  # true hull area for utilization
    base_hull = simplify_hull(base_hull)
    infl = inflate_hull(base_hull, spacing / 2.0)

    angles = _angles(angle_step_deg)

    # Pre-rotate the inflated hull about the origin for each candidate angle.
    angle_data = []
    for rot in angles:
        rot_infl = _transform(infl, 1.0, rot, 0.0, 0.0)
        mnx, mny, mxx, mxy = _bbox(rot_infl)
        angle_data.append((rot, rot_infl, mnx, mny, mxx - mnx, mxy - mny))

    xs = _grid(pack_w)
    ys = _grid(pack_d)

    placed: list[tuple[list[Point], tuple[float, float, float, float]]] = []
    # A reserved tower rect (inflated by spacing/2) is pre-placed so parts nest
    # around it; it is never counted in placements or utilization.
    if reserve is not None:
        rx, ry, rw, rd = reserve
        if rw > 0 and rd > 0:
            rect = [(rx, ry), (rx + rw, ry), (rx + rw, ry + rd), (rx, ry + rd)]
            rinfl = inflate_hull(rect, spacing / 2.0)
            placed.append((rinfl, _bbox(rinfl)))
    placements: list[Placement] = []
    union: list[float] | None = None  # [minx, miny, maxx, maxy]

    target = count if count is not None else 10_000
    # Cells where no rotation fits stay unfittable (placed parts never move),
    # so they are cached and skipped on later instances.
    dead: set[tuple[float, float]] = set()
    for _ in range(target):
        chosen = _place_one(angle_data, xs, ys, pack_w, pack_d, placed, union, dead)
        if chosen is None:
            break
        rot, tx, ty, cand, cbb = chosen
        placed.append((cand, cbb))
        placements.append(Placement(x=tx, y=ty, rot_deg=rot, scale=scale))
        if union is None:
            union = [cbb[0], cbb[1], cbb[2], cbb[3]]
        else:
            union[0] = min(union[0], cbb[0])
            union[1] = min(union[1], cbb[1])
            union[2] = max(union[2], cbb[2])
            union[3] = max(union[3], cbb[3])

    n = len(placements)
    if count is None and n >= target:
        warnings.append(f"auto-fill stopped at the {target}-instance cap")
    fits_requested = True
    if count is not None and n < count:
        fits_requested = False
        warnings.append(
            f"requested {count} but only {n} fit on {bed_w:g}x{bed_d:g} bed"
        )
    if n == 0:
        warnings.append("no instances placed")

    bed_area = bed_w * bed_d
    util = (n * base_area / bed_area) if bed_area > 0 else 0.0

    return PackResult(
        placements=placements,
        scale=scale,
        fits_requested=fits_requested,
        bed_utilization=util,
        warnings=warnings,
    )


def _grid(extent: float) -> list[float]:
    vals: list[float] = []
    v = 0.0
    while v < extent - _EPS:
        vals.append(v)
        v += _GRID_STEP
    return vals


def _place_one(angle_data, xs, ys, bed_w, bed_d, placed, union, dead):
    """Find the lowest (y, x) cell where some rotation fits; return placement."""
    for gy in ys:
        for gx in xs:
            if (gx, gy) in dead:
                continue
            fitting = []
            for rot, rot_infl, mnx, mny, w, d in angle_data:
                if gx + w > bed_w + 1e-6 or gy + d > bed_d + 1e-6:
                    continue
                tx, ty = gx - mnx, gy - mny
                cand = [(px + tx, py + ty) for px, py in rot_infl]
                cbb = (gx, gy, gx + w, gy + d)
                if _overlaps_any(cand, cbb, placed):
                    continue
                fitting.append((rot, tx, ty, cand, cbb))
            if fitting:
                return _best_by_union(fitting, union)
            dead.add((gx, gy))
    return None


def _overlaps_any(cand, cbb, placed) -> bool:
    cminx, cminy, cmaxx, cmaxy = cbb
    for poly, bb in placed:
        if cmaxx <= bb[0] + _EPS or bb[2] <= cminx + _EPS:
            continue
        if cmaxy <= bb[1] + _EPS or bb[3] <= cminy + _EPS:
            continue
        if polygons_overlap(cand, poly):
            return True
    return False


def _best_by_union(fitting, union):
    best = None
    best_area = math.inf
    for entry in fitting:  # angles ascending -> ties keep smallest rotation
        cbb = entry[4]
        if union is None:
            area = (cbb[2] - cbb[0]) * (cbb[3] - cbb[1])
        else:
            w = max(union[2], cbb[2]) - min(union[0], cbb[0])
            h = max(union[3], cbb[3]) - min(union[1], cbb[1])
            area = w * h
        if area < best_area - _EPS:
            best_area = area
            best = entry
    return best


# --------------------------------------------------------------------------- #
# Bitmap packer (v2): concave silhouette nesting + lattice pattern mode
# --------------------------------------------------------------------------- #


def _bitmap_angles(angle_step_deg: float) -> list[float]:
    """Rotation angles for the v2 packer.

    Restricted to multiples of ``max(angle_step_deg, 45)`` to stay inside the
    pure-Python performance budget (a full 24-angle sweep at raster resolution
    is too slow). This still yields up to 8 orientations and covers the
    lattice thetas {0, 90} (+ {45, 135} when angle_step <= 45). Documented
    deviation from "angles from angle_step" in the design.
    """
    step = max(angle_step_deg, 45.0)
    if step <= 0 or step >= 360:
        return [0.0]
    out: list[float] = []
    a = 0.0
    while a < 360.0 - _EPS:
        out.append(a)
        a += step
    return out


def _finalize_v2(placements, scale, base_area, bed_w, bed_d, count, method):
    warnings: list[str] = []
    n = len(placements)
    cap = count if count is not None else 10_000
    if count is None and n >= cap:
        warnings.append(f"auto-fill stopped at the {cap}-instance cap")
    fits_requested = True
    if count is not None and n < count:
        fits_requested = False
        warnings.append(
            f"requested {count} but only {n} fit on {bed_w:g}x{bed_d:g} bed"
        )
    if n == 0:
        warnings.append("no instances placed")
    bed_area = bed_w * bed_d
    util = (n * base_area / bed_area) if bed_area > 0 else 0.0
    return PackResult(
        placements=placements,
        scale=scale,
        fits_requested=fits_requested,
        bed_utilization=util,
        warnings=warnings,
        method=method,
    )


# --------------------------------------------------------------------------- #
# Layout centring (rigid shift of the whole layout onto the bed centre)
# --------------------------------------------------------------------------- #


def _center_shift(lo: float, hi: float, span: float) -> float:
    """Shift that centres ``[lo, hi]`` in ``[0, span]``, clamped to stay inside."""
    ideal = span / 2.0 - (lo + hi) / 2.0
    low, high = -lo, span - hi
    if low > high:
        return 0.0
    return max(low, min(high, ideal))


def _center_hull(result, footprint_xy, spacing, pack_w, pack_d, reserve):
    """Recentre a hull-mode layout on the bed as a rigid group (packing coords).

    Only the fixed reserve rect can be collided with under a rigid shift, so the
    ideal shift is tried at full/half/quarter strength against the inflated
    reserve and dropped if none is clear."""
    pls = result.placements
    if not pls:
        return
    hull0 = convex_hull(footprint_xy)
    base_hull = simplify_hull([(x * result.scale, y * result.scale)
                               for x, y in hull0])
    infl = inflate_hull(base_hull, spacing / 2.0)
    polys = [_transform(infl, 1.0, p.rot_deg, p.x, p.y) for p in pls]
    bbs = [_bbox(poly) for poly in polys]
    minx = min(b[0] for b in bbs)
    miny = min(b[1] for b in bbs)
    maxx = max(b[2] for b in bbs)
    maxy = max(b[3] for b in bbs)
    sx = _center_shift(minx, maxx, pack_w)
    sy = _center_shift(miny, maxy, pack_d)

    if reserve is not None and reserve[2] > 0 and reserve[3] > 0:
        rx, ry, rw, rd = reserve
        rect = inflate_hull(
            [(rx, ry), (rx + rw, ry), (rx + rw, ry + rd), (rx, ry + rd)],
            spacing / 2.0,
        )
        sx, sy = 0.0, 0.0
        for frac in (1.0, 0.5, 0.25):
            tsx, tsy = _center_shift(minx, maxx, pack_w) * frac, \
                _center_shift(miny, maxy, pack_d) * frac
            if not any(
                polygons_overlap([(x + tsx, y + tsy) for x, y in poly], rect)
                for poly in polys
            ):
                sx, sy = tsx, tsy
                break

    if sx or sy:
        for p in pls:
            p.x += sx
            p.y += sy


def _center_v2(result, masks, pack_w, pack_d, reserve):
    """Recentre a bitmap/lattice layout on the bed, quantised to whole cells."""
    pls = result.placements
    if not pls:
        return
    from . import bitmap

    wcells = int(math.floor(pack_w / CELL + 1e-9))
    hcells = int(math.floor(pack_d / CELL + 1e-9))
    cells: list[tuple] = []
    minx = miny = math.inf
    maxx = maxy = -math.inf
    for p in pls:
        m = masks[p.rot_deg]
        gx = int(round((p.x + m.offset_x) / CELL))
        gy = int(round((p.y + m.offset_y) / CELL))
        cells.append((m, gx, gy))
        minx, miny = min(minx, gx), min(miny, gy)
        maxx, maxy = max(maxx, gx + m.width), max(maxy, gy + m.height)

    scx = int(round(_center_shift(minx, maxx, wcells)))
    scy = int(round(_center_shift(miny, maxy, hcells)))

    if reserve is not None and reserve[2] > 0 and reserve[3] > 0:
        scx, scy = 0, 0
        ix = int(round(_center_shift(minx, maxx, wcells)))
        iy = int(round(_center_shift(miny, maxy, hcells)))
        for frac in (1.0, 0.5, 0.25):
            tcx, tcy = int(round(ix * frac)), int(round(iy * frac))
            bed = bitmap.BedGrid(pack_w, pack_d, CELL)
            bed.reserve_rect(*reserve)
            if all(bed.can_place(m, gx + tcx, gy + tcy) for m, gx, gy in cells):
                scx, scy = tcx, tcy
                break

    if scx or scy:
        for p in pls:
            p.x += scx * CELL
            p.y += scy * CELL


def _best_angle_union(fitting, masks, gx, gy, ub):
    """Pick the fitting angle whose placement grows the union bbox least."""
    best = None
    best_area = math.inf
    for a in fitting:  # angles ascending -> ties keep smallest rotation
        m = masks[a]
        x0, y0, x1, y1 = gx, gy, gx + m.width, gy + m.height
        if ub is None:
            area = (x1 - x0) * (y1 - y0)
        else:
            w = max(ub[2], x1) - min(ub[0], x0)
            h = max(ub[3], y1) - min(ub[1], y0)
            area = w * h
        if area < best_area - _EPS:
            best_area = area
            best = a
    return best


def _bitmap_greedy(bed, masks, angles, remaining, scale, placements, ub):
    """Bottom-left greedy fill of ``bed`` with the given masks.

    Appends to ``placements`` (in place) up to ``remaining`` parts, returning
    the running union bbox ``ub`` (cells, or None). Cells where no angle fits
    stay dead (occupancy only grows), so they are cached and skipped.
    """
    step = GREEDY_STEP
    xs = list(range(0, bed.wcells, step))
    ys = list(range(0, bed.hcells, step))
    dead: set[tuple[int, int]] = set()
    while remaining > 0:
        chosen = None
        for gy in ys:
            for gx in xs:
                if (gx, gy) in dead:
                    continue
                fitting = [a for a in angles if bed.can_place(masks[a], gx, gy)]
                if fitting:
                    chosen = (_best_angle_union(fitting, masks, gx, gy, ub), gx, gy)
                    break
                dead.add((gx, gy))
            if chosen:
                break
        if chosen is None:
            break
        a, gx, gy = chosen
        m = masks[a]
        bed.place(m, gx, gy)
        placements.append(
            Placement(x=gx * CELL - m.offset_x, y=gy * CELL - m.offset_y,
                      rot_deg=a, scale=scale)
        )
        ub = _extend_ub(ub, gx, gy, m.width, m.height)
        remaining -= 1
    return ub


def _extend_ub(ub, gx, gy, w, h):
    if ub is None:
        return [gx, gy, gx + w, gy + h]
    ub[0] = min(ub[0], gx)
    ub[1] = min(ub[1], gy)
    ub[2] = max(ub[2], gx + w)
    ub[3] = max(ub[3], gy + h)
    return ub


def _pack_bitmap(masks, angles, bed_w, bed_d, count, scale, reserve=None):
    from . import bitmap

    bed = bitmap.BedGrid(bed_w, bed_d, CELL)
    if reserve is not None:
        bed.reserve_rect(*reserve)
    remaining = count if count is not None else 10_000
    placements: list[Placement] = []
    _bitmap_greedy(bed, masks, angles, remaining, scale, placements, None)
    return placements


# -- lattice ---------------------------------------------------------------- #


def _pair_union(a, b, dx, dy):
    """(min_x, min_y, width, height) of a base mask + partner at (dx, dy)."""
    minx = min(0, dx)
    miny = min(0, dy)
    maxx = max(a.width, dx + b.width)
    maxy = max(a.height, dy + b.height)
    return minx, miny, maxx - minx, maxy - miny


def _search_pairs(a, b, spacing):
    """Best few flipped-partner offsets (dx, dy) that don't collide.

    Scans a window of +/-(part bbox + spacing) at 2-cell steps; keeps the
    tightest (smallest union bbox) non-colliding offsets. Deterministic.
    """
    from . import bitmap

    span = max(a.width, a.height, b.width, b.height) + math.ceil(spacing / CELL)
    scored: list[tuple[int, int, int]] = []  # (area, dx, dy)
    for dx in range(-span, span + 1, 2):
        for dy in range(-span, span + 1, 2):
            if bitmap.masks_overlap(a, b, dx, dy):
                continue
            _mx, _my, w, h = _pair_union(a, b, dx, dy)
            scored.append((w * h, dx, dy))
    scored.sort()
    return [(dx, dy) for _area, dx, dy in scored[:5]]


def _tiling_free(a, b, dx, dy, px, py, sx=0):
    """Whether a 3x3 tiling of the (base, partner) pair is collision-free.

    Checks the centre pair's two parts against all 8 neighbour pairs; lattice
    translation symmetry makes that sufficient. ``sx`` staggers each row's
    x-origin by ``n*sx`` (a brick/shear lattice; ``sx=0`` is the rigid grid).
    """
    from . import bitmap

    ov = bitmap.masks_overlap
    for m in (-1, 0, 1):
        for n in (-1, 0, 1):
            if m == 0 and n == 0:
                continue
            ox, oy = m * px + n * sx, n * py
            if ov(a, a, ox, oy):                       # A_c vs A_n
                return False
            if ov(a, b, ox + dx, oy + dy):             # A_c vs B_n
                return False
            if ov(b, a, ox - dx, oy - dy):             # B_c vs A_n
                return False
            if ov(b, b, ox, oy):                       # B_c vs B_n
                return False
    return True


def _shrink_pitch(a, b, dx, dy):
    """Shrink the lattice pitches while a 3x3 tiling stays collision-free.

    Smaller pitches let neighbouring pairs interlock (columns/rows overlap).
    """
    _mx, _my, px, py = _pair_union(a, b, dx, dy)
    while px > 1 and _tiling_free(a, b, dx, dy, px - 1, py):
        px -= 1
    while py > 1 and _tiling_free(a, b, dx, dy, px, py - 1):
        py -= 1
    return px, py


def _stagger_steps(px, stagger):
    """Candidate row shifts ``sx`` in ``[0, px)`` at 2-cell steps (0 included).

    ``stagger=False`` returns ``[0]`` (rigid grid). Deterministic order.
    """
    if not stagger or px <= 1:
        return [0]
    return list(range(0, px, 2))


def _fit_py_stagger(a, b, dx, dy, px, py0, sx):
    """Minimal collision-free row pitch for stagger ``sx``, seeded from ``py0``.

    Staggered rows can drop lower than the rigid pitch; a shift can also demand
    a slightly taller pitch, so grow first if ``py0`` collides, then shrink.
    Returns ``None`` when no valid pitch is found (skip this ``sx``).
    """
    py = py0
    ceil = py0 + max(a.height, b.height) + 1
    while py < ceil and not _tiling_free(a, b, dx, dy, px, py, sx):
        py += 1
    if not _tiling_free(a, b, dx, dy, px, py, sx):
        return None
    while py > 1 and _tiling_free(a, b, dx, dy, px, py - 1, sx):
        py -= 1
    return py


def _lattice_rows(a, b, dx, dy, px, py, sx, bed_wc, bed_hc):
    """Per-row column counts for a (possibly staggered) lattice.

    Row ``n`` has x-origin shifted by ``n*sx`` (``sx >= 0``, never negative),
    so its column count is computed individually. Returns the list of column
    counts indexed by row; ``sum`` of it is the pair-node count.
    """
    if px <= 0 or py <= 0:
        return []
    ax0 = max(0, -dx)
    ay0 = max(0, -dy)
    base_right = ax0 + max(a.width, dx + b.width)
    base_top = ay0 + max(a.height, dy + b.height)
    rows: list[int] = []
    n = 0
    while base_top + n * py <= bed_hc:
        avail = bed_wc - (base_right + n * sx)
        rows.append(avail // px + 1 if avail >= 0 else 0)
        n += 1
    return rows


def _lattice_thetas(masks, angle_step_deg):
    base = [0.0, 90.0]
    if angle_step_deg <= 45:
        base += [45.0, 135.0]
    return [t for t in base if t in masks and (t + 180.0) % 360.0 in masks]


def _lattice_candidate(masks, angle_step_deg, bed_wc, bed_hc, stagger):
    """Best (parts-maximising) lattice pattern; ``None`` if nothing tiles.

    Returns ``(key, theta, dx, dy, px, py, sx)``. ``stagger`` enables the
    row-shift search (``sx``); ``False`` restricts to the rigid grid (``sx=0``).
    """
    best = None
    for th in _lattice_thetas(masks, angle_step_deg):
        a = masks[th]
        b = masks[(th + 180.0) % 360.0]
        for dx, dy in _search_pairs(a, b, spacing=2.0 * CELL):
            px, py0 = _shrink_pitch(a, b, dx, dy)
            for sx in _stagger_steps(px, stagger):
                py = _fit_py_stagger(a, b, dx, dy, px, py0, sx)
                if py is None:
                    continue
                rows = _lattice_rows(a, b, dx, dy, px, py, sx, bed_wc, bed_hc)
                parts = 2 * sum(rows)
                key = (parts, -(px * py), -th, -dx, -dy, -sx)
                if best is None or key > best[0]:
                    best = (key, th, dx, dy, px, py, sx)
    return best


def _pack_one_lattice(masks, angles, bed_w, bed_d, bed_wc, bed_hc, count, scale,
                      candidate, reserve):
    """Place one lattice ``candidate`` pattern, then greedily fill the rest."""
    from . import bitmap

    bed = bitmap.BedGrid(bed_w, bed_d, CELL)
    if reserve is not None:
        bed.reserve_rect(*reserve)
    placements: list[Placement] = []
    remaining = count if count is not None else 10_000
    ub = None

    if candidate is not None and candidate[0][0] > 0:
        _key, th, dx, dy, px, py, sx = candidate
        a = masks[th]
        b = masks[(th + 180.0) % 360.0]
        ax0 = max(0, -dx)
        ay0 = max(0, -dy)
        rows = _lattice_rows(a, b, dx, dy, px, py, sx, bed_wc, bed_hc)
        for n, m_cnt in enumerate(rows):  # bottom-left order: rows outer
            for m in range(m_cnt):
                gx = ax0 + m * px + n * sx
                gy = ay0 + n * py
                for mask, ex, ey in ((a, 0, 0), (b, dx, dy)):
                    if remaining <= 0:
                        break
                    if bed.can_place(mask, gx + ex, gy + ey):
                        bed.place(mask, gx + ex, gy + ey)
                        placements.append(
                            Placement(x=(gx + ex) * CELL - mask.offset_x,
                                      y=(gy + ey) * CELL - mask.offset_y,
                                      rot_deg=th if mask is a else (th + 180.0) % 360.0,
                                      scale=scale)
                        )
                        ub = _extend_ub(ub, gx + ex, gy + ey, mask.width, mask.height)
                        remaining -= 1

    _bitmap_greedy(bed, masks, angles, remaining, scale, placements, ub)
    return placements


def _pack_lattice(masks, angles, bed_w, bed_d, count, scale, angle_step_deg,
                  reserve=None, stagger=True):
    bed_wc = int(math.floor(bed_w / CELL + 1e-9))
    bed_hc = int(math.floor(bed_d / CELL + 1e-9))

    cand = _lattice_candidate(masks, angle_step_deg, bed_wc, bed_hc, stagger)
    placements = _pack_one_lattice(masks, angles, bed_w, bed_d, bed_wc, bed_hc,
                                   count, scale, cand, reserve)
    # A staggered pattern can occasionally leave worse greedy-fill gaps than the
    # rigid grid; keep whichever actually places more so stagger never regresses.
    if stagger:
        rigid = _lattice_candidate(masks, angle_step_deg, bed_wc, bed_hc, False)
        if rigid is not None and (cand is None or rigid[1:] != cand[1:]):
            rigid_pl = _pack_one_lattice(masks, angles, bed_w, bed_d, bed_wc,
                                         bed_hc, count, scale, rigid, reserve)
            if len(rigid_pl) > len(placements):
                placements = rigid_pl
    return placements


# --------------------------------------------------------------------------- #
# Silhouette (top-down outline of the actual part, for visualization)
# --------------------------------------------------------------------------- #


def silhouette_rings(
    points: list[Point], resolution: int = 128
) -> list[list[Point]]:
    """Trace the top-down outline of a part from its projected vertices.

    Bins the XY points into a grid, then walks the boundary of the occupied
    region into closed rings (mm coordinates). Dense sculpted meshes give a
    faithful concave outline. Returns [] when vertex coverage is too sparse to
    infer the interior (low-poly CAD shapes) — callers should fall back to the
    convex hull then.
    """
    if len(points) < 3:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny)
    if span <= _EPS:
        return []
    c = span / resolution  # square cells
    occ: set[tuple[int, int]] = set()
    for x, y in points:
        occ.add((int((x - minx) / c), int((y - miny) / c)))
    # close one-cell gaps between sampled vertices
    occ |= {(i + di, j + dj) for i, j in occ for di in (-1, 0, 1) for dj in (-1, 0, 1)}

    hull_area = _polygon_area(convex_hull(points))
    if hull_area > _EPS and len(occ) * c * c < 0.35 * hull_area:
        return []  # too sparse: outline would be dots, not a shape

    # boundary edges of the occupied region, oriented so interior is on the left
    seg: dict[tuple[int, int], list[tuple[int, int]]] = {}

    def emit(a: tuple[int, int], b: tuple[int, int]) -> None:
        seg.setdefault(a, []).append(b)

    for i, j in occ:
        if (i, j - 1) not in occ:
            emit((i, j), (i + 1, j))
        if (i + 1, j) not in occ:
            emit((i + 1, j), (i + 1, j + 1))
        if (i, j + 1) not in occ:
            emit((i + 1, j + 1), (i, j + 1))
        if (i - 1, j) not in occ:
            emit((i, j + 1), (i, j))

    rings: list[list[Point]] = []
    while seg:
        start = next(iter(seg))
        ring_idx: list[tuple[int, int]] = [start]
        cur = seg[start].pop()
        if not seg[start]:
            del seg[start]
        while cur != start:
            ring_idx.append(cur)
            nxts = seg.get(cur)
            if not nxts:
                break  # open chain (shouldn't happen); drop it
            cur = nxts.pop()
            if not seg.get(ring_idx[-1]):
                seg.pop(ring_idx[-1], None)
        else:
            ring = [
                (minx + i * c, miny + j * c) for i, j in ring_idx
            ]
            rings.append(_merge_collinear(ring))
    return rings


def _merge_collinear(ring: list[Point]) -> list[Point]:
    if len(ring) < 3:
        return ring
    out: list[Point] = []
    n = len(ring)
    for i in range(n):
        prev, cur, nxt = ring[i - 1], ring[i], ring[(i + 1) % n]
        cross = (cur[0] - prev[0]) * (nxt[1] - cur[1]) - (
            cur[1] - prev[1]
        ) * (nxt[0] - cur[0])
        if abs(cross) > _EPS:
            out.append(cur)
    return out or ring


# --------------------------------------------------------------------------- #
# SVG preview
# --------------------------------------------------------------------------- #


def preview_svg(
    result: PackResult,
    footprint_xy: list[Point],
    bed_w: float = 270.0,
    bed_d: float = 270.0,
    reserve: tuple[float, float, float, float] | None = None,
    margin: float = 0.0,
) -> str:
    """Self-contained top-down SVG of the packed layout (units: mm).

    ``reserve`` is an optional ``(x, y, w, d)`` mm rectangle drawn as a hatched
    grey prime-tower block. ``margin`` (when > 0) draws a dashed inner rectangle
    marking the bed-edge keep-out that parts stay clear of.
    """
    hull = convex_hull(footprint_xy)
    n = len(result.placements)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="-8 -8 {_num(bed_w + 16)} {_num(bed_d + 16)}" '
        f'width="{_num(bed_w)}mm" height="{_num(bed_d)}mm">',
        f'<rect x="0" y="0" width="{_num(bed_w)}" height="{_num(bed_d)}" '
        f'fill="#f4f5f7" stroke="none"/>',
    ]
    # 10 mm grid (light) with 50 mm majors, like a printer bed.
    step = 10.0
    v = step
    while v < min(bed_w, bed_d) - _EPS or v < max(bed_w, bed_d) - _EPS:
        major = abs(v % 50.0) < _EPS
        color = "#c9cdd4" if major else "#e3e5e9"
        if v < bed_w - _EPS:
            parts.append(
                f'<line x1="{_num(v)}" y1="0" x2="{_num(v)}" y2="{_num(bed_d)}" '
                f'stroke="{color}" stroke-width="0.4"/>'
            )
        if v < bed_d - _EPS:
            parts.append(
                f'<line x1="0" y1="{_num(bed_d - v)}" x2="{_num(bed_w)}" '
                f'y2="{_num(bed_d - v)}" stroke="{color}" stroke-width="0.4"/>'
            )
        v += step
    parts.append(
        f'<rect x="0" y="0" width="{_num(bed_w)}" height="{_num(bed_d)}" '
        f'fill="none" stroke="#333" stroke-width="1"/>'
    )
    # origin marker + bed size label
    parts.append(
        f'<circle cx="0" cy="{_num(bed_d)}" r="2" fill="#2f6feb"/>'
    )
    parts.append(
        f'<text x="{_num(bed_w - 2)}" y="{_num(bed_d - 2)}" font-size="6" '
        f'text-anchor="end" fill="#8b93a1">{_num(bed_w)}×{_num(bed_d)} mm</text>'
    )
    # Edge-margin keep-out: dashed inner rectangle at the inset boundary.
    if margin > 0 and bed_w - 2 * margin > 0 and bed_d - 2 * margin > 0:
        parts.append(
            f'<rect x="{_num(margin)}" y="{_num(margin)}" '
            f'width="{_num(bed_w - 2 * margin)}" height="{_num(bed_d - 2 * margin)}" '
            f'fill="none" stroke="#b0455a" stroke-width="0.4" '
            f'stroke-dasharray="3 2" opacity="0.6"/>'
        )
        parts.append(
            f'<text x="{_num(margin + 2)}" y="{_num(margin + 6)}" font-size="4" '
            f'fill="#b0455a" opacity="0.7">{_num(margin)} mm edge margin</text>'
        )
    # Reserved prime-tower block: hatched grey rect (flip Y for top-down view).
    if reserve is not None and reserve[2] > 0 and reserve[3] > 0:
        rx, ry, rw, rd = reserve
        sy = bed_d - (ry + rd)
        parts.append(
            '<defs><pattern id="tower" width="4" height="4" '
            'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            '<rect width="4" height="4" fill="#d8dbe0"/>'
            '<line x1="0" y1="0" x2="0" y2="4" stroke="#9aa0ab" '
            'stroke-width="1"/></pattern></defs>'
        )
        parts.append(
            f'<rect x="{_num(rx)}" y="{_num(sy)}" width="{_num(rw)}" '
            f'height="{_num(rd)}" fill="url(#tower)" stroke="#9aa0ab" '
            f'stroke-width="0.5"/>'
        )
        parts.append(
            f'<text x="{_num(rx + rw / 2)}" y="{_num(sy + rd / 2)}" font-size="5" '
            f'text-anchor="middle" fill="#6b7280">tower</text>'
        )
    # Actual part outline: traced silhouette when vertex coverage allows,
    # else the convex hull. Defined once, stamped per instance via <use>.
    rings = silhouette_rings(footprint_xy)
    if not rings:
        rings = [hull]
    path_d: list[str] = []
    for ring in rings:
        # pre-flip Y so per-instance transforms stay a plain rotate/scale
        coords = [(px, -py) for px, py in ring]
        path_d.append(
            "M "
            + " L ".join(f"{_num(px)} {_num(py)}" for px, py in coords)
            + " Z"
        )
    parts.append(
        f'<defs><path id="part" fill-rule="evenodd" d="{" ".join(path_d)}"/></defs>'
    )

    for i, pl in enumerate(result.placements):
        poly = _transform(hull, pl.scale, pl.rot_deg, pl.x, pl.y)
        # flip Y so mm-up maps to SVG-down for an intuitive top-down view
        flipped = [(x, bed_d - y) for x, y in poly]
        pts = " ".join(f"{_num(x)},{_num(y)}" for x, y in flipped)
        hue = (i * 360.0 / max(n, 1)) % 360.0
        color = f"hsl({_num(hue)}, 70%, 55%)"
        cx = sum(p[0] for p in flipped) / len(flipped)
        cy = sum(p[1] for p in flipped) / len(flipped)
        # spacing envelope (hull), dashed + translucent
        parts.append(
            f'<polygon points="{pts}" fill="{color}" fill-opacity="0.12" '
            f'stroke="{color}" stroke-width="0.4" stroke-dasharray="2 1.5"/>'
        )
        # actual part silhouette (fill on the group: inherited reliably by <use>)
        parts.append(
            f'<g fill="{color}" fill-opacity="0.9" stroke="#222" stroke-width="0.3" '
            f'transform="translate({_num(pl.x)} {_num(bed_d - pl.y)}) '
            f'rotate({_num(-pl.rot_deg)}) scale({_num(pl.scale)})">'
            f'<use href="#part" xlink:href="#part"/></g>'
        )
        parts.append(
            f'<text x="{_num(cx)}" y="{_num(cy)}" font-size="6" '
            f'text-anchor="middle" fill="#000">{i + 1}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _num(v: float) -> str:
    v = float(v)
    if v == 0.0:
        return "0"
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s
