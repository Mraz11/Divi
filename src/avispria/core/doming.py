# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The doming check: is the whole 3D model bent into a dome or a bowl?

Photos all taken straight down, without ground control points, let a small error in the lens
model bend the whole surface (James & Robson 2014): the middle rises or sinks against the edges
by up to metres, and every height (and the area-wide canopy height) is off by a pattern, not by
noise. It is caught by comparing this flight's ground with an independent ground model (a LiDAR
model, a global model, an earlier survey) where the ground was seen: after removing the overall
offset, a curved difference is the dome.

The difference is fitted with z = a + b x + c y + d x^2 + e y^2 + f x y over the seen-ground
cells. The dome is the rise or fall of the curved part (the d, e, f terms) from the middle of
the area to its edge. Positive: the middle stands too high (a dome); negative: a bowl.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

MIN_CELLS = 200
MIN_SPREAD = 0.3  # the seen ground must reach this share of the area's width and height
WARN_M = 0.5  # a dome larger than this, and larger than twice the noise, is reported


@dataclass(frozen=True)
class DomeCheck:
    checked: bool
    dome_m: float | None  # middle minus edge of the curved part; + dome, - bowl
    noise_m: float | None  # spread of the difference left after the fit (robust sd)
    cells: int
    domed: bool
    note: str


def _robust_sd(values: FloatArray) -> float:
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def check_doming(
    ground: FloatArray, reference: FloatArray, seen: BoolArray, cell_m: float
) -> DomeCheck:
    """Compare this flight's ``ground`` with an independent ``reference`` where ``seen``."""
    use = seen & np.isfinite(ground) & np.isfinite(reference)
    n = int(use.sum())
    rows, cols = np.nonzero(use)
    if n < MIN_CELLS:
        return DomeCheck(False, None, None, n, False, "too little seen ground to check")
    h, w = ground.shape
    if np.ptp(rows) < MIN_SPREAD * h or np.ptp(cols) < MIN_SPREAD * w:
        return DomeCheck(False, None, None, n, False, "the seen ground is in one corner only")
    # centred, in metres, so the terms are well conditioned
    y = (rows - (h - 1) / 2) * cell_m
    x = (cols - (w - 1) / 2) * cell_m
    diff = ground[use] - reference[use]
    diff = diff - np.median(diff)
    design = np.column_stack([np.ones(n), x, y, x * x, y * y, x * y])
    coef, *_ = np.linalg.lstsq(design, diff, rcond=None)
    noise = _robust_sd(diff - design @ coef)
    # the curved part over the whole area: middle (0, 0) against the mean of the four corners
    xs = np.array([-1, 1, -1, 1]) * (w - 1) / 2 * cell_m
    ys = np.array([-1, -1, 1, 1]) * (h - 1) / 2 * cell_m
    edge = float(np.mean(coef[3] * xs**2 + coef[4] * ys**2 + coef[5] * xs * ys))
    dome = -edge  # the curved part is 0 in the middle
    domed = abs(dome) > max(WARN_M, 2 * noise)
    shape = "dome (middle too high)" if dome > 0 else "bowl (middle too low)"
    note = (
        f"a {shape} of {abs(dome):.2f} m from the middle to the corners"
        if domed
        else f"no doming found (curve {dome:+.2f} m, noise {noise:.2f} m)"
    )
    return DomeCheck(True, round(dome, 3), round(noise, 3), n, domed, note)


def not_checked() -> DomeCheck:
    return DomeCheck(
        False,
        None,
        None,
        0,
        False,
        "not checked: give an independent ground model (a LiDAR model, Copernicus GLO-30, an "
        "earlier survey) to check; flights with only straight-down photos and no ground control "
        "points are the ones at risk",
    )
