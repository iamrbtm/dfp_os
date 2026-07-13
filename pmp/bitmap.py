"""Bitboard raster geometry for concave (silhouette) nesting (pure stdlib).

The convex-hull packer in :mod:`multipack.packing` can never interlock concave
parts (an ear or tail slotting into a neighbour's notch), because it collision-
tests hulls. This module rasterises the *true* top-down silhouette of a part
into a bitboard so concave shapes can nest tight.

Cell / placement convention
---------------------------
A part is rasterised on a square grid of ``cell`` mm. A :class:`PartMask` stores
one Python int per row (bit ``i`` set == cell ``(i, j)`` occupied) plus the mm
coordinate of cell ``(0, 0)``'s min corner in the part's un-translated
scaled+rotated frame (``offset_x, offset_y``).

Placing a mask at bed grid cell ``(gx, gy)`` aligns mask cell ``(0, 0)``'s min
corner to bed mm ``(gx*cell, gy*cell)``. The matching :class:`packing.Placement`
translation is therefore::

    tx = gx*cell - offset_x
    ty = gy*cell - offset_y

so that ``final_xy = rotate(scale*p, rot) + (tx, ty)`` (the packing.Placement /
compose_transform convention) lands the part with its rasterised footprint's
min corner at ``(gx*cell, gy*cell)``.

Spacing is baked in: every mask is Euclidean-disk dilated by
``ceil((spacing/2)/cell)`` cells. Two dilated masks that do not share a cell keep
the true parts >= ``spacing`` apart; a dilated mask inside the bed keeps the true
part >= ``spacing/2`` from the edges. Radii round up, so the guarantee is
conservative.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .packing import _EPS, _polygon_area, convex_hull

Point = tuple[float, float]
Cell = tuple[int, int]

# Fraction of the convex-hull area that must be raster-occupied for a point
# cloud to count as a faithful silhouette (matches silhouette_rings).
_DENSITY_FRAC = 0.35


# --------------------------------------------------------------------------- #
# Raster primitives
# --------------------------------------------------------------------------- #


def rasterize_points(points: list[Point], cell: float) -> set[Cell]:
    """Bin ``points`` into ``cell``-mm cells, then close 1-cell gaps.

    Cells are indexed relative to the min corner of the point cloud. The
    8-neighbourhood dilation bridges gaps between sparsely sampled vertices,
    the same trick used by ``silhouette_rings``.
    """
    if not points:
        return set()
    minx = min(p[0] for p in points)
    miny = min(p[1] for p in points)
    inv = 1.0 / cell
    occ: set[Cell] = set()
    for x, y in points:
        occ.add((int(math.floor((x - minx) * inv)), int(math.floor((y - miny) * inv))))
    closed = set(occ)
    for i, j in occ:
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                closed.add((i + di, j + dj))
    return closed


def _hline_x(poly: list[Point], y: float) -> tuple[float, float] | None:
    xs: list[float] = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 <= y < y2) or (y2 <= y < y1):
            t = (y - y1) / (y2 - y1)
            xs.append(x1 + t * (x2 - x1))
    if not xs:
        return None
    return min(xs), max(xs)


def rasterize_convex(hull: list[Point], cell: float) -> set[Cell]:
    """Conservative scanline fill of a convex polygon (rounds outward).

    Used as a fallback when a point cloud is too sparse to raster faithfully
    (low-poly CAD shapes). Cells are indexed relative to the hull's min corner.
    """
    if len(hull) < 3:
        return rasterize_points(hull, cell)
    minx = min(p[0] for p in hull)
    miny = min(p[1] for p in hull)
    maxy = max(p[1] for p in hull)
    inv = 1.0 / cell
    occ: set[Cell] = set()
    jmax = int(math.floor((maxy - miny) * inv))
    for j in range(jmax + 1):
        y0 = miny + j * cell
        y1 = miny + (j + 1) * cell
        lo, hi = math.inf, -math.inf
        for yy in (y0, 0.5 * (y0 + y1), y1):
            yc = min(max(yy, miny), maxy - 1e-12)
            span = _hline_x(hull, yc)
            if span:
                lo = min(lo, span[0])
                hi = max(hi, span[1])
        if lo > hi:
            continue
        i0 = int(math.floor((lo - minx) * inv))
        i1 = int(math.floor((hi - minx) * inv))
        for i in range(i0, i1 + 1):
            occ.add((i, j))
    return occ


def dilate(cells: set[Cell], radius_cells: int) -> set[Cell]:
    """Euclidean disk dilation: add every cell within ``radius_cells``.

    Offsets ``(dx, dy)`` with ``dx*dx + dy*dy <= radius_cells**2``.
    """
    if radius_cells <= 0:
        return set(cells)
    r = int(radius_cells)
    r2 = r * r
    offsets = [
        (dx, dy)
        for dx in range(-r, r + 1)
        for dy in range(-r, r + 1)
        if dx * dx + dy * dy <= r2
    ]
    out: set[Cell] = set()
    for i, j in cells:
        for dx, dy in offsets:
            out.add((i + dx, j + dy))
    return out


# --------------------------------------------------------------------------- #
# Part mask
# --------------------------------------------------------------------------- #


@dataclass
class PartMask:
    rows: list[int]
    width: int
    height: int
    offset_x: float
    offset_y: float


def _mask_from_cells(cells: set[Cell], minx: float, miny: float, cell: float) -> PartMask:
    if not cells:
        return PartMask([], 0, 0, minx, miny)
    mini = min(i for i, _ in cells)
    minj = min(j for _, j in cells)
    maxi = max(i for i, _ in cells)
    maxj = max(j for _, j in cells)
    width = maxi - mini + 1
    height = maxj - minj + 1
    rows = [0] * height
    for i, j in cells:
        rows[j - minj] |= 1 << (i - mini)
    return PartMask(rows, width, height, minx + mini * cell, miny + minj * cell)


def _rotate(points: list[Point], deg: float) -> list[Point]:
    th = math.radians(deg)
    c, s = math.cos(th), math.sin(th)
    return [(c * x - s * y, s * x + c * y) for x, y in points]


def dense_enough(points: list[Point], cell: float, hull_area: float) -> bool:
    """Whether a point cloud raster-fills enough of its hull to be a silhouette.

    Mirrors the ``silhouette_rings`` sparsity test: occupied area must reach
    ``_DENSITY_FRAC`` of the convex-hull area.
    """
    if hull_area <= _EPS:
        return False
    occ = rasterize_points(points, cell)
    return len(occ) * cell * cell >= _DENSITY_FRAC * hull_area


def make_masks(
    points_scaled: list[Point],
    angles_deg: list[float],
    spacing: float,
    cell: float,
    hull_area: float | None = None,
) -> dict[float, PartMask]:
    """Build one spacing-dilated :class:`PartMask` per rotation angle.

    For each angle: rotate the (already scaled) points about the origin,
    rasterise (points, or a convex fill when too sparse), then dilate by
    ``ceil((spacing/2)/cell)`` cells to bake in spacing/2.
    """
    if hull_area is None:
        hull_area = _polygon_area(convex_hull(points_scaled))
    r_cells = math.ceil((spacing / 2.0) / cell) if spacing > 0 else 0
    masks: dict[float, PartMask] = {}
    for ang in angles_deg:
        rot = _rotate(points_scaled, ang)
        minx = min(p[0] for p in rot)
        miny = min(p[1] for p in rot)
        occ = rasterize_points(rot, cell)
        if hull_area > _EPS and len(occ) * cell * cell < _DENSITY_FRAC * hull_area:
            occ = rasterize_convex(convex_hull(rot), cell)
        occ = dilate(occ, r_cells)
        masks[ang] = _mask_from_cells(occ, minx, miny, cell)
    return masks


# --------------------------------------------------------------------------- #
# Mask collision + bed
# --------------------------------------------------------------------------- #


def masks_overlap(a: PartMask, b: PartMask, dx: int, dy: int) -> bool:
    """Whether mask ``a`` at the origin overlaps mask ``b`` offset by ``(dx, dy)``.

    Handles negative offsets by normalising both x-shifts to be non-negative.
    """
    if not a.rows or not b.rows:
        return False
    ax = max(0, -dx)  # a's absolute x shift
    bx = max(0, dx)   # b's absolute x shift (bx - ax == dx)
    r0 = max(0, dy)
    r1 = min(a.height, dy + b.height)
    for r in range(r0, r1):
        if (a.rows[r] << ax) & (b.rows[r - dy] << bx):
            return True
    return False


class BedGrid:
    """Occupancy bitboard for the bed. Rows are Python ints (bit i == cell i)."""

    def __init__(self, bed_w: float, bed_d: float, cell: float) -> None:
        self.cell = cell
        self.wcells = int(math.floor(bed_w / cell + 1e-9))
        self.hcells = int(math.floor(bed_d / cell + 1e-9))
        self.rows: list[int] = [0] * self.hcells

    def can_place(self, mask: PartMask, gx: int, gy: int) -> bool:
        if gx < 0 or gy < 0:
            return False
        if gx + mask.width > self.wcells or gy + mask.height > self.hcells:
            return False
        rows = self.rows
        mrows = mask.rows
        for j in range(mask.height):
            if (mrows[j] << gx) & rows[gy + j]:
                return False
        return True

    def place(self, mask: PartMask, gx: int, gy: int) -> None:
        rows = self.rows
        mrows = mask.rows
        for j in range(mask.height):
            rows[gy + j] |= mrows[j] << gx

    def reserve_rect(self, x: float, y: float, w: float, d: float) -> None:
        """Mark every cell touched by the mm rectangle ``(x, y, w, d)`` occupied.

        Used to keep a prime/wipe tower's footprint clear. Masks are already
        dilated by ``spacing/2``, so blocking the raw rect keeps parts
        ``>= spacing/2`` from it. Rounds outward (whole touched cells)."""
        if w <= 0 or d <= 0:
            return
        inv = 1.0 / self.cell
        i0 = max(0, int(math.floor(x * inv)))
        j0 = max(0, int(math.floor(y * inv)))
        i1 = min(self.wcells - 1, int(math.floor((x + w) * inv)))
        j1 = min(self.hcells - 1, int(math.floor((y + d) * inv)))
        if i1 < i0 or j1 < j0:
            return
        band = ((1 << (i1 - i0 + 1)) - 1) << i0
        for j in range(j0, j1 + 1):
            self.rows[j] |= band
