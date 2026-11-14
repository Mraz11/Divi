# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single tree crowns from a canopy height model, and the condition of each crown.

Crowns: tree tops are local maxima of the smoothed canopy height, searched in a window that
grows with height (tall trees have wide crowns); a marker watershed then grows each top down to
the crown's edge (``scipy.ndimage.watershed_ift``).

Condition: the share of a crown that is not green (excess green at or below GREEN_THRESHOLD) is
a dieback score: dead or dying crowns lose their leaves or turn yellow-brown, which an RGB camera
sees. A roof, a water tank or a parked truck is also tall and not green, so crowns that are flat
planes (a robust plane fit leaves almost no residual) are marked as structures, not trees.

What it cannot see: stress before symptoms (that needs near-infrared), and colour at low sun is
dominated by orange light and shadow, so the dieback score is flagged unreliable then.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi

from avispria.core.canopy import GREEN_THRESHOLD, TREE_HEIGHT_M
from avispria.core.safety import Issue

FloatArray = NDArray[np.float64]
TOP_MIN_M = 5.0  # a tree top must stand at least this high
MIN_CROWN_M2 = 2.0  # smaller segments are noise
DIEBACK_SHARE = 0.5  # half the crown not green: a dieback candidate
FLAT_RESIDUAL_M = 0.25  # a crown this close to a plane is a built structure
FLAT_LOCAL_M = 0.15  # height spread within 1.5 m below which a surface is a roof, not leaves
BUILT_SHARE = 0.4  # this much of a crown on flat, not-green surface: a structure
LOW_SUN_DEG = 25.0


@dataclass(frozen=True)
class Crown:
    id: int
    row: float  # tree top, in grid cells
    col: float
    height_m: float
    area_m2: float
    diameter_m: float  # of a circle with the same area
    not_green: float | None  # 0..1 share of the crown that is not green; None without colour
    lightness: float | None  # CIE L* mean, 0..100
    redness: float | None  # CIE a* mean: brown and red crowns are positive
    yellowness: float | None  # CIE b* mean
    plane_residual_m: float
    structure: bool
    dieback: bool


@dataclass(frozen=True)
class CrownReport:
    crowns: list[Crown]
    labels: NDArray[np.int32]  # crown id per cell, 0 = none
    trees: int
    structures: int
    dieback_candidates: int
    issues: list[Issue] = field(default_factory=list)


def search_radius_cells(height_m: FloatArray, cell_m: float) -> NDArray[np.int64]:
    """Half-width of the tree-top window: about a third of a typical crown radius for the height
    (1.5 m for low trees, 4 m for 40 m trees)."""
    radius_m = np.clip(1.0 + 0.075 * height_m, 1.5, 4.0)
    return np.maximum(1, np.round(radius_m / cell_m)).astype(np.int64)


def tree_tops(smooth: FloatArray, cell_m: float) -> NDArray[np.int32]:
    """Markers 1..n at the tree tops (0 elsewhere)."""
    radii = search_radius_cells(smooth, cell_m)
    is_top = np.zeros(smooth.shape, dtype=bool)
    for r in np.unique(radii):
        local_max = ndi.maximum_filter(smooth, size=2 * int(r) + 1, mode="nearest")
        is_top |= (radii == r) & (smooth >= local_max) & (smooth >= TOP_MIN_M)
    labels, _ = ndi.label(is_top)  # a flat top of several cells is one tree
    return np.asarray(labels, dtype=np.int32)


def refine_tops(
    markers: NDArray[np.int32], smooth: FloatArray, boxes: list[tuple[int, int, int, int]]
) -> tuple[NDArray[np.int32], int, int]:
    """Correct the tree tops with crown boxes from a detector (rows/cols: r0, c0, r1, c1).

    * a box with no tree top inside, over canopy, gets one at its highest cell: a tree the
      height model merged into a neighbour;
    * two or more tops in the middle half of one box become one tree: a crown the height model
      split in two.
    Returns the new markers and how many tops were added and merged."""
    out = markers.copy()
    added = merged = 0
    next_id = int(out.max()) + 1
    h, w = out.shape
    for r0, c0, r1, c1 in boxes:
        r0, c0, r1, c1 = max(0, r0), max(0, c0), min(h, r1), min(w, c1)
        if r1 - r0 < 2 or c1 - c0 < 2:
            continue
        inside = out[r0:r1, c0:c1]
        ids = np.unique(inside[inside > 0])
        if ids.size == 0:
            patch = smooth[r0:r1, c0:c1]
            r, c = np.unravel_index(int(np.argmax(patch)), patch.shape)
            if patch[r, c] >= TREE_HEIGHT_M:
                out[r0 + r, c0 + c] = next_id
                next_id += 1
                added += 1
            continue
        qr, qc = (r1 - r0) // 4, (c1 - c0) // 4
        middle = out[r0 + qr : r1 - qr, c0 + qc : c1 - qc]
        central = np.unique(middle[middle > 0])
        if central.size >= 2:
            out[np.isin(out, central[1:])] = central[0]
            merged += central.size - 1
    return out, added, merged


def segment(
    chm: FloatArray, cell_m: float, boxes: list[tuple[int, int, int, int]] | None = None
) -> NDArray[np.int32]:
    """Crown id per cell (0 = no crown) by a marker watershed on the inverted canopy height;
    ``boxes`` (from a crown detector, in grid cells) correct the tree tops first."""
    if cell_m <= 0:
        raise ValueError("cell_m must be positive")
    valid = ~np.isnan(chm)
    height = np.where(valid, chm, 0.0)
    smooth = ndi.gaussian_filter(height, sigma=max(0.5, 0.5 / cell_m))
    markers = tree_tops(smooth, cell_m)
    if boxes:
        markers, _, _ = refine_tops(markers, smooth, boxes)
    canopy = valid & (smooth >= TREE_HEIGHT_M)
    markers = np.where(canopy | (markers > 0), markers, -1).astype(np.int32)
    top = float(smooth.max()) if smooth.size else 0.0
    relief = np.clip((top - smooth) * 100.0, 0, 65535).astype(np.uint16)  # cm, depth below top
    grown = ndi.watershed_ift(relief, markers)
    labels = np.where(canopy & (grown > 0), grown, 0).astype(np.int32)
    return _drop_small(labels, cell_m)


def _drop_small(labels: NDArray[np.int32], cell_m: float) -> NDArray[np.int32]:
    ids, counts = np.unique(labels[labels > 0], return_counts=True)
    small = ids[counts * cell_m * cell_m < MIN_CROWN_M2]
    out = np.where(np.isin(labels, small), 0, labels)
    keep = np.unique(out[out > 0])
    lookup = np.zeros(int(labels.max()) + 1, dtype=np.int32)
    lookup[keep] = np.arange(1, keep.size + 1, dtype=np.int32)
    return np.asarray(lookup[out], dtype=np.int32)


def srgb_to_lab(rgb: FloatArray) -> FloatArray:
    """CIE L*a*b* (D65) from 8-bit sRGB in the last axis."""
    c = np.clip(rgb / 255.0, 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def local_spread(height: FloatArray, cell_m: float, window_m: float = 1.5) -> FloatArray:
    """Standard deviation of height in a small window: leaves are rough, roofs are smooth."""
    size = max(3, round(window_m / cell_m) | 1)
    mean = ndi.uniform_filter(height, size=size, mode="nearest")
    square = ndi.uniform_filter(height * height, size=size, mode="nearest")
    return np.asarray(np.sqrt(np.clip(square - mean * mean, 0.0, None)))


def _plane_residual(z: FloatArray, rows: FloatArray, cols: FloatArray, cell_m: float) -> float:
    """Median absolute residual of a least-squares plane through the crown surface (m)."""
    if z.size < 4:
        return 0.0
    a = np.column_stack([rows * cell_m, cols * cell_m, np.ones_like(z)])
    coef, *_ = np.linalg.lstsq(a, z, rcond=None)
    return float(np.median(np.abs(z - a @ coef)))


def analyse_crowns(
    chm: FloatArray,
    cell_m: float,
    rgb: FloatArray | None = None,
    sun_elevation_deg: float | None = None,
    boxes: list[tuple[int, int, int, int]] | None = None,
) -> CrownReport:
    """Crowns, their size and height, and (with colour, ``rgb`` shaped rows x cols x 3) their
    condition. ``boxes``: crowns found by a detector (grid cells), to correct the tree tops."""
    labels = segment(chm, cell_m, boxes)
    height = np.nan_to_num(chm)
    lab = None if rgb is None else srgb_to_lab(rgb)
    green = None
    if rgb is not None:
        total = rgb.sum(axis=-1)
        with np.errstate(invalid="ignore", divide="ignore"):
            exg = (2 * rgb[..., 1] - rgb[..., 0] - rgb[..., 2]) / total
        green = np.nan_to_num(exg, nan=0.0) > GREEN_THRESHOLD
    built = (local_spread(height, cell_m) < FLAT_LOCAL_M) & (height >= TREE_HEIGHT_M)
    if green is not None:
        built &= ~green
    crowns: list[Crown] = []
    for i, where in enumerate(ndi.find_objects(labels), start=1):
        if where is None:
            continue
        inside = labels[where] == i
        z = height[where][inside]
        rr, cc = np.nonzero(inside)
        top = int(np.argmax(z))
        area = float(inside.sum()) * cell_m * cell_m
        residual = _plane_residual(z, rr.astype(float), cc.astype(float), cell_m)
        flat = built[where][inside]
        natural = inside.copy()
        natural[inside] = ~flat  # judge a crown's colour on its leaves, not on a roof beside it
        structure = float(flat.mean()) >= BUILT_SHARE or (
            residual < FLAT_RESIDUAL_M and (green is None or not green[where][inside].mean() > 0.5)
        )
        share = None
        if green is not None and natural.any():
            share = float(1.0 - green[where][natural].mean())
        colour = None if lab is None else lab[where][inside].mean(axis=0)
        dieback = (
            share is not None
            and share >= DIEBACK_SHARE
            and not structure
            and float(z.max()) >= TOP_MIN_M
        )
        crowns.append(
            Crown(
                id=i,
                row=float(rr[top] + where[0].start),
                col=float(cc[top] + where[1].start),
                height_m=round(float(z.max()), 2),
                area_m2=round(area, 2),
                diameter_m=round(2 * float(np.sqrt(area / np.pi)), 2),
                not_green=None if share is None else round(share, 3),
                lightness=None if colour is None else round(float(colour[0]), 1),
                redness=None if colour is None else round(float(colour[1]), 2),
                yellowness=None if colour is None else round(float(colour[2]), 2),
                plane_residual_m=round(residual, 3),
                structure=structure,
                dieback=dieback,
            )
        )
    issues: list[Issue] = []
    candidates = sum(c.dieback for c in crowns)
    if rgb is not None and sun_elevation_deg is not None and sun_elevation_deg < LOW_SUN_DEG:
        issues.append(
            Issue(
                "warning",
                "CH003",
                f"the sun was {sun_elevation_deg:.0f} degrees up: crown colours are dominated by "
                "orange light and shadow, so the dieback candidates are unreliable; fly between "
                "mid-morning and early afternoon to judge crown condition",
            )
        )
    return CrownReport(
        crowns=crowns,
        labels=labels,
        trees=sum(not c.structure for c in crowns),
        structures=sum(c.structure for c in crowns),
        dieback_candidates=candidates,
        issues=issues,
    )
