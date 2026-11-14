# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Correct tree heights with trees measured in the field.

Heights from photogrammetry are biased: the tops of crowns are smoothed away (Young et al. 2021
found -0.5 to -0.8 m) and the ground under closed canopy is guessed too high (Swinfield et al.
2019: about -5 m in tropical forest). The bias depends on the site, the flight and the
processing, so it is measured, not assumed: a handful of trees whose height was measured on the
ground (laser rangefinder or clinometer) are matched to the crowns, and

* 5 or more trees: a straight line field = a + b x model (Swinfield et al. 2019)
* 2 to 4 trees: an offset only, field = model + a
* fewer: no correction (the heights are reported as the model gives them)

Both the raw and the corrected heights are always reported, with the fit's error before and
after, and a leave-one-out error that says how well the correction carries to trees not used to
make it. The spread left after the fit is the height uncertainty used for biomass.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
MIN_LINE = 5
MIN_OFFSET = 2
MATCH_M = 3.0  # a field tree further than this from every tree top is not matched
SLOPE_RANGE = (0.5, 2.0)  # outside this the line is not believed; the offset is used instead


@dataclass(frozen=True)
class HeightCalibration:
    method: str  # "line", "offset" or "none"
    intercept_m: float
    slope: float
    matched: int
    unmatched: int
    rmse_before_m: float | None
    rmse_after_m: float | None
    rmse_loo_m: float | None  # leave-one-out: the error on trees not used in the fit
    residual_sd_m: float | None  # the height uncertainty after correction
    pairs: tuple[tuple[str, float, float], ...]  # (field id, model height, field height)
    note: str

    def apply(self, heights: FloatArray) -> FloatArray:
        return np.asarray(self.intercept_m + self.slope * heights, dtype=float)


NONE = HeightCalibration(
    "none", 0.0, 1.0, 0, 0, None, None, None, None, (), "no field heights: not corrected"
)


def _fit(model: FloatArray, field: FloatArray, line: bool) -> tuple[float, float, str]:
    if line and np.ptp(model) > 0:
        slope, intercept = np.polyfit(model, field, 1)
        if SLOPE_RANGE[0] <= slope <= SLOPE_RANGE[1]:
            return float(intercept), float(slope), "line"
    return float(np.mean(field - model)), 1.0, "offset"


def _rmse(values: FloatArray) -> float:
    return float(np.sqrt(np.mean(values**2)))


def calibrate(
    tops_xy: FloatArray, tops_height: FloatArray, field: list[tuple[str, float, float, float]]
) -> HeightCalibration:
    """Match field trees (id, x, y, height; x/y in the model's coordinates) to tree tops
    (``tops_xy`` n x 2) and fit the correction."""
    if not field:
        return NONE
    pairs = []
    unmatched = 0
    for name, x, y, h in field:
        if len(tops_xy) == 0:
            unmatched += 1
            continue
        d = np.hypot(tops_xy[:, 0] - x, tops_xy[:, 1] - y)
        i = int(np.argmin(d))
        if d[i] > MATCH_M:
            unmatched += 1
            continue
        pairs.append((name, float(tops_height[i]), float(h)))
    n = len(pairs)
    if n < MIN_OFFSET:
        return HeightCalibration(
            "none", 0.0, 1.0, n, unmatched, None, None, None, None, tuple(pairs),
            f"only {n} field tree(s) matched a tree top (2 needed): not corrected",
        )  # fmt: skip
    model = np.array([p[1] for p in pairs])
    truth = np.array([p[2] for p in pairs])
    intercept, slope, method = _fit(model, truth, n >= MIN_LINE)
    after = truth - (intercept + slope * model)
    loo = []
    for k in range(n):
        keep = np.arange(n) != k
        a, b, _ = _fit(model[keep], truth[keep], keep.sum() >= MIN_LINE)
        loo.append(truth[k] - (a + b * model[k]))
    dof = max(1, n - (2 if method == "line" else 1))
    resid_sd = float(np.sqrt(np.sum(after**2) / dof))
    before = _rmse(truth - model)
    return HeightCalibration(
        method,
        round(intercept, 3),
        round(slope, 4),
        n,
        unmatched,
        round(before, 3),
        round(_rmse(after), 3),
        round(_rmse(np.array(loo)), 3),
        round(resid_sd, 3),
        tuple(pairs),
        f"{n} field trees: model heights were {float(np.mean(model - truth)):+.2f} m off on "
        f"average (error {before:.2f} m); after the {method} correction {_rmse(after):.2f} m "
        f"(on trees left out of the fit: {_rmse(np.array(loo)):.2f} m)",
    )
