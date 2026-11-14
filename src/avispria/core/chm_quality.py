# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Quality checks of a canopy height model, and one grade for it: good, use with care, or poor.

Each check looks for a known way photogrammetric canopy heights go wrong:
* holes: places with no surface (moving leaves in wind, too little overlap, water);
* ground above the surface: the ground model does not fit this flight (wrong datum, a shifted
  outside model, or an engine ground pushed up by the canopy);
* spikes: heights no tree reaches (matching errors, birds, wires);
* hidden ground: under a closed canopy the ground was hardly seen, so it is guessed and the
  heights are biased low unless the ground came from a better source;
* doming: the whole model bent (see doming.py);
* the ground's own uncertainty where the trees stand.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from avispria.core.doming import DomeCheck

FloatArray = NDArray[np.float64]

HOLES_WARN_PCT, HOLES_POOR_PCT = 5.0, 20.0
BELOW_WARN_PCT, BELOW_POOR_PCT = 2.0, 10.0
BELOW_M = 0.5
SPIKE_WARN_PCT = 0.1
MAX_TREE_M = 70.0  # taller than nearly every tree outside a few temperate rainforests
SEEN_WARN_PCT = 10.0
SIGMA_WARN_M, SIGMA_POOR_M = 1.5, 3.0


@dataclass(frozen=True)
class ChmQuality:
    grade: str  # "good", "use with care", "poor"
    holes_pct: float
    ground_above_pct: float
    spikes_pct: float
    ground_seen_pct: float
    ground_sigma_at_trees_m: float | None
    doming: DomeCheck
    findings: list[str] = field(default_factory=list)


def check_chm(
    dsm: FloatArray,
    ground: FloatArray,
    inside: NDArray[np.bool_],
    seen_pct: float,
    sigma_at_trees: FloatArray,
    doming: DomeCheck,
    ground_from_outside: bool,
    max_tree_m: float = MAX_TREE_M,
) -> ChmQuality:
    """``inside``: the cells of the mapped area (after the edge trim)."""
    area = max(1, int(inside.sum()))
    holes = float((inside & ~np.isfinite(dsm)).sum() / area * 100)
    with np.errstate(invalid="ignore"):
        diff = dsm - ground
        below = float((inside & (diff < -BELOW_M)).sum() / area * 100)
        spikes = float((inside & (diff > max_tree_m)).sum() / area * 100)
    sigma = float(np.median(sigma_at_trees)) if sigma_at_trees.size else None
    findings: list[str] = []
    level = 0  # 0 good, 1 care, 2 poor

    def add(severity: int, text: str) -> None:
        nonlocal level
        level = max(level, severity)
        findings.append(text)

    if holes >= HOLES_WARN_PCT:
        add(
            2 if holes >= HOLES_POOR_PCT else 1,
            f"{holes:.0f}% of the area has no surface (wind in the leaves, too little overlap)",
        )
    if below >= BELOW_WARN_PCT:
        add(
            2 if below >= BELOW_POOR_PCT else 1,
            f"the ground model lies above the surface on {below:.0f}% of the area: it does not "
            "fit this flight (datum, shift, or ground pushed up by the canopy)",
        )
    if spikes >= SPIKE_WARN_PCT:
        add(1, f"{spikes:.1f}% of the area is higher than {max_tree_m:.0f} m: spikes, ignored")
    if seen_pct < SEEN_WARN_PCT and not ground_from_outside:
        add(
            1,
            f"the ground was seen on only {seen_pct:.0f}% of the area: under the canopy it is "
            "guessed and heights are likely too low; give a LiDAR, leaf-off or global ground "
            "model, or correct the heights with field-measured trees",
        )
    if sigma is not None and sigma >= SIGMA_WARN_M:
        add(
            2 if sigma >= SIGMA_POOR_M else 1,
            f"the ground under the trees is uncertain by about {sigma:.1f} m",
        )
    if doming.domed:
        add(2 if abs(doming.dome_m or 0) > 2 else 1, f"doming: {doming.note}")
    elif not doming.checked:
        findings.append(f"doming {doming.note}")
    grade = ("good", "use with care", "poor")[level]
    return ChmQuality(
        grade,
        round(holes, 1),
        round(below, 1),
        round(spikes, 2),
        round(seen_pct, 1),
        None if sigma is None else round(sigma, 2),
        doming,
        findings,
    )
