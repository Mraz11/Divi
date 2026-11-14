# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canopy height from a surface model: ground, height above ground, cover, gaps and tree tops.

A drone's surface model (DSM) is the top of whatever the camera saw: tree crowns, roofs, open
ground. Canopy height is the DSM minus the bare ground (DTM). Photographs only see the ground
where the canopy is open, so the ground under a closed canopy is always an interpolation; every
result says how much of the area the ground was actually seen in (``ground_seen_pct``).

The ground comes either from the engine (ODX's DTM, made by classifying its point cloud) or, when
there is none, is estimated here with a morphological opening of the DSM: the lowest surface in a
window as wide as the widest crown. That estimate is only sound where open ground occurs within
every window; ``issues`` say when it was not.

Grids are north-up arrays in metres; NaN is "no data" and is never filled silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import NDArray

from avispria.core.safety import Issue

FloatArray = NDArray[np.float64]

TREE_HEIGHT_M = 2.0  # above this a cell counts as canopy (a common forestry threshold)
GROUND_TOLERANCE_M = 0.5  # a DSM cell this close to the ground means the ground was seen
TOP_MIN_HEIGHT_M = 5.0  # local maxima lower than this are not counted as tree tops
MIN_GROUND_SEEN_PCT = 10.0  # below this the ground is mostly guessed
GREEN_THRESHOLD = 0.02  # excess-green index above this counts as green vegetation (a proxy)


@dataclass(frozen=True)
class CanopyStats:
    cell_m: float
    area_m2: float
    ground_source: str  # a kind of core.ground_sources (engine, estimated, lidar, ...)
    ground_seen_pct: float
    canopy_cover_pct: float  # share of the mapped area with canopy height >= TREE_HEIGHT_M
    gap_pct: float  # share of the mapped area below TREE_HEIGHT_M
    height_mean_m: float  # over canopy cells only
    height_p50_m: float
    height_p95_m: float
    height_max_m: float
    tree_tops: int  # local maxima of canopy height: a rough count of crowns
    tree_tops_per_ha: float
    tall_not_green_pct: float = 0.0  # tall cells left out as not green (roofs, vehicles, ...)
    issues: list[Issue] = field(default_factory=list)


def _axis_extreme(values: FloatArray, radius: int, axis: int, mode: str) -> FloatArray:
    if radius <= 0:
        return values
    fill = -np.inf if mode == "max" else np.inf
    pad = [(0, 0), (0, 0)]
    pad[axis] = (radius, radius)
    windows = sliding_window_view(
        np.pad(values, pad, constant_values=fill), 2 * radius + 1, axis=axis
    )
    reducer = np.max if mode == "max" else np.min
    return np.asarray(reducer(windows, axis=-1), dtype=float)


def extreme(values: FloatArray, radius: int, mode: Literal["min", "max"]) -> FloatArray:
    """Square min or max filter of half-width ``radius`` cells; NaN cells are ignored."""
    fill = -np.inf if mode == "max" else np.inf
    work = np.where(np.isnan(values), fill, values)
    work = _axis_extreme(work, radius, axis=1, mode=mode)
    work = _axis_extreme(work, radius, axis=0, mode=mode)
    return np.where(np.isinf(work), np.nan, work)


def _window_sum(a: FloatArray, radius: int) -> FloatArray:
    """Sum over the square window of half-width ``radius`` around every cell (zero padding)."""
    size = 2 * radius + 1
    c = np.pad(np.pad(a, radius).cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
    return np.asarray(c[size:, size:] - c[:-size, size:] - c[size:, :-size] + c[:-size, :-size])


def neighbour_mean(values: FloatArray, radius: int) -> FloatArray:
    """Mean of the valid cells in each window, NaN only where the window holds none."""
    valid = ~np.isnan(values)
    total = _window_sum(np.where(valid, values, 0.0), radius)
    count = _window_sum(valid.astype(float), radius)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0.5, total / np.maximum(count, 1.0), np.nan)


def box_mean(values: FloatArray, radius: int) -> FloatArray:
    """Mean of the valid cells in a square window (a light smoothing); NaN stays NaN."""
    if radius <= 0:
        return values.copy()
    return np.where(np.isnan(values), np.nan, neighbour_mean(values, radius))


def ground_cells(
    dsm: FloatArray,
    cell_m: float,
    max_window_m: float = 80.0,
    slope: float = 0.15,
    dh0_m: float = 0.3,
    dh_max_m: float = 2.5,
) -> NDArray[np.bool_]:
    """Cells that look like bare ground: a progressive morphological filter (Zhang et al. 2003).

    Openings with windows doubling up to ``max_window_m`` remove ever larger objects; a cell that
    stands higher above an opening than that window's height tolerance (growing with ``slope``,
    capped at ``dh_max_m``) is not ground. ``max_window_m`` must exceed the widest stand of trees
    with no open ground in it.
    """
    if cell_m <= 0 or max_window_m <= 0:
        raise ValueError("cell_m and max_window_m must be positive")
    surface = dsm.copy()
    ground = ~np.isnan(dsm)
    radius, previous_width = 1, cell_m
    while True:
        width = (2 * radius + 1) * cell_m
        opened = extreme(extreme(surface, radius, "min"), radius, "max")
        dh = min(dh_max_m, dh0_m + slope * (width - previous_width))
        ground &= ~((dsm - opened) > dh)
        surface = np.where(np.isnan(opened), surface, opened)
        if width >= max_window_m:
            return ground
        previous_width, radius = width, radius * 2


def fill_from(points: FloatArray, valid: NDArray[np.bool_]) -> FloatArray:
    """Fill every cell from the nearest valid cells, coarsest gaps last (windows that grow)."""
    known = np.where(valid, points, np.nan)
    out = known.copy()
    radius = 1
    while np.isnan(out).any() and radius <= 2 * max(out.shape):
        out = np.where(np.isnan(out), neighbour_mean(known, radius), out)
        radius *= 2
    return out


def estimate_ground(dsm: FloatArray, cell_m: float, max_window_m: float = 80.0) -> FloatArray:
    """Bare-ground model from a DSM: ground cells kept, the rest interpolated between them."""
    keep = ground_cells(dsm, cell_m, max_window_m)
    if not keep.any():
        raise ValueError("no cell looks like bare ground: the ground cannot be estimated")
    ground = fill_from(dsm, keep)
    ground = box_mean(ground, max(1, round(1.0 / cell_m)))
    return np.where(np.isnan(dsm), np.nan, np.minimum(ground, dsm))


def excess_green(red: FloatArray, green: FloatArray, blue: FloatArray) -> FloatArray:
    """Normalised excess-green index (2g - r - b), -1..2; a proxy for green vegetation only.

    RGB cannot tell a living crown from a green roof or a dry crown from soil: this index only
    separates green surfaces from grey, brown and white ones, and needs checking in the field.
    """
    total = red + green + blue
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(total > 0, (2 * green - red - blue) / total, np.nan)


def canopy_height(dsm: FloatArray, dtm: FloatArray) -> FloatArray:
    """Height above ground (m); small negative values from noise are clipped to zero."""
    if dsm.shape != dtm.shape:
        raise ValueError(f"DSM {dsm.shape} and DTM {dtm.shape} must be on the same grid")
    return np.clip(dsm - dtm, 0.0, None)


def tree_tops(chm: FloatArray, cell_m: float, radius_m: float = 2.5) -> int:
    """Local maxima of canopy height above TOP_MIN_HEIGHT_M within ``radius_m``."""
    radius = max(1, round(radius_m / cell_m))
    smooth = box_mean(chm, 1)
    peaks = (smooth == extreme(smooth, radius, "max")) & (smooth >= TOP_MIN_HEIGHT_M)
    return int(np.count_nonzero(peaks))


def summarize(
    dsm: FloatArray,
    dtm: FloatArray,
    cell_m: float,
    ground_source: str,  # a kind of core.ground_sources
    green: NDArray[np.bool_] | None = None,
) -> tuple[FloatArray, CanopyStats]:
    """Canopy height model and its statistics over the cells where both grids have data.

    ``green`` (same grid) marks green surfaces; tall cells that are not green (roofs, vehicles)
    are then left out of the canopy figures but kept in the height model itself.
    """
    chm = canopy_height(dsm, dtm)
    valid = ~np.isnan(chm)
    n = int(np.count_nonzero(valid))
    if n == 0:
        raise ValueError("the surface and ground models do not overlap")
    values = chm[valid]
    tall = values >= TREE_HEIGHT_M
    is_green = np.ones_like(tall) if green is None else green[valid]
    not_green = tall & ~is_green
    canopy = values[tall & is_green]
    seen = float(np.mean(values <= GROUND_TOLERANCE_M) * 100.0)
    area = n * cell_m * cell_m
    tops = tree_tops(chm if green is None else np.where(green, chm, 0.0), cell_m)
    issues: list[Issue] = []
    if seen < MIN_GROUND_SEEN_PCT and ground_source in ("engine", "estimated"):
        issues.append(
            Issue(
                "warning",
                "CH001",
                f"the ground was seen in only {seen:.0f}% of the area: canopy heights rest on a "
                "guessed ground; fly in leaf-off season, include open ground, or use a ground "
                "model from LiDAR",
            )
        )
    if ground_source == "estimated":
        issues.append(
            Issue(
                "warning",
                "CH002",
                "the ground was estimated from the surface model itself (no engine ground model): "
                "heights are approximate, check them against a few trees measured in the field",
            )
        )
    stats = CanopyStats(
        cell_m=cell_m,
        area_m2=area,
        ground_source=ground_source,
        ground_seen_pct=round(seen, 1),
        canopy_cover_pct=round(canopy.size / n * 100.0, 1),
        gap_pct=round(float(np.count_nonzero(~tall)) / n * 100.0, 1),
        height_mean_m=round(float(canopy.mean()), 2) if canopy.size else 0.0,
        height_p50_m=round(float(np.percentile(canopy, 50)), 2) if canopy.size else 0.0,
        height_p95_m=round(float(np.percentile(canopy, 95)), 2) if canopy.size else 0.0,
        height_max_m=round(float(canopy.max()), 2) if canopy.size else 0.0,
        tree_tops=tops,
        tree_tops_per_ha=round(tops / (area / 10_000.0), 1),
        tall_not_green_pct=round(float(np.count_nonzero(not_green)) / n * 100.0, 1),
        issues=issues,
    )
    return chm, stats
