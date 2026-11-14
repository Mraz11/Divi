# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shadows cast by a surface model under a known sun.

A cell is in shadow when something between it and the sun rises above the sun's ray through it.
Walking from each cell toward the sun in steps of one cell, the ray climbs ``step * tan(elev)``
per step; any cell above the ray casts the shadow. All cells walk together (array shifts), so the
cost is one pass per step, and the walk stops once the ray is above the highest surface.

Used twice: to *predict* where the photos are dark because of shade (so dark is not mistaken for
water or soil), and to answer planning questions such as "how much of the street do the trees
shade at 2 pm in April".
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
MAX_WALK_M = 300.0  # longer shadows than this are not followed (sun below about 3 degrees)


def _shift(values: FloatArray, dy: int, dx: int) -> FloatArray:
    """``values`` moved so that out[r, c] = values[r + dy, c + dx]; outside is -inf."""
    out = np.full(values.shape, -np.inf)
    rows, cols = values.shape
    r0, r1 = max(0, -dy), min(rows, rows - dy)
    c0, c1 = max(0, -dx), min(cols, cols - dx)
    if r0 < r1 and c0 < c1:
        out[r0:r1, c0:c1] = values[r0 + dy : r1 + dy, c0 + dx : c1 + dx]
    return out


def shadow_mask(
    surface: FloatArray, cell_m: float, sun_elevation_deg: float, sun_azimuth_deg: float
) -> NDArray[np.bool_]:
    """Cells of ``surface`` (north-up, metres; NaN = no data) in shadow for the given sun.

    Azimuth is clockwise from north. With the sun at or below the horizon everything is shaded.
    """
    if cell_m <= 0:
        raise ValueError("cell_m must be positive")
    valid = ~np.isnan(surface)
    if sun_elevation_deg <= 0:
        return valid.copy()
    z = np.where(valid, surface, -np.inf)
    rise = math.tan(math.radians(sun_elevation_deg)) * cell_m  # per one-cell step
    az = math.radians(sun_azimuth_deg)
    east, north = math.sin(az), math.cos(az)  # toward the sun
    top = float(np.max(z[valid])) if valid.any() else 0.0
    shaded = np.zeros(surface.shape, dtype=bool)
    steps = int(min(MAX_WALK_M / cell_m, max(1.0, (top - np.min(z[valid])) / rise + 1)))
    for k in range(1, steps + 1):
        dx, dy = round(k * east), round(-k * north)  # rows grow southward
        ahead = _shift(z, dy, dx)
        shaded |= ahead > z + k * rise
    return shaded & valid


def shaded_share(mask: NDArray[np.bool_], where: NDArray[np.bool_]) -> float:
    """Share (0..1) of the cells in ``where`` that are shaded; 0 when ``where`` is empty."""
    n = int(np.count_nonzero(where))
    return float(np.count_nonzero(mask & where)) / n if n else 0.0
