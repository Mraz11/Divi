# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where the ground under the trees comes from, ranked, and how sure each place is.

Photogrammetry cannot see the ground under a closed canopy, so the ground it reports there is
guessed, and too high: canopy heights come out too low (Swinfield et al. 2019 found a mean bias
of about 5 m in tropical forest). The ground model is therefore the first thing that decides how
good every canopy number is. The sources, best first:

1. ``lidar``     a laser-scanned ground model (sees through gaps in the leaves)
2. ``leaf-off``  a ground model from a flight when the leaves were off, or after harvest
3. ``survey``    ground heights measured on the ground (GNSS, total station), interpolated
4. ``engine``    the ground the engine classified from this flight's points (SMRF), good where
                 the ground was seen (open land, towns), poor under closed canopy
5. ``global``    a global elevation model (Copernicus GLO-30, SRTM): coarse (30 m) but not
                 fooled by the canopy
6. ``estimated`` Dīvi's own guess from the lowest points of this flight's surface model

Under a closed canopy (the ground seen in less than ``CLOSED_CANOPY_SEEN_PCT`` of the area) a
global model is preferred to this flight's own ground, which there is mostly the canopy.

Every outside model is moved up or down to meet this flight's surface where the ground was seen:
the heights of a drone's photos are above the ellipsoid, those of most elevation models above
the geoid (tens of metres apart in South Asia), and a consumer drone's height is off by metres.
The move is recorded.

The uncertainty of the ground at each place (``ground_sigma``) is the source's own error, plus,
for ground guessed from this flight, a part that grows with the distance to the nearest place
where the ground was actually seen. These numbers are stated assumptions, chosen from the
literature, not measurements; they are written into every summary.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

KINDS = ("lidar", "leaf-off", "survey", "engine", "global", "estimated")
OUTSIDE_KINDS = ("lidar", "leaf-off", "survey", "global")  # given as a file
KIND_TEXT = {
    "lidar": "laser-scanned ground model",
    "leaf-off": "ground model from a leaf-off or after-harvest flight",
    "survey": "ground measured on the ground and interpolated",
    "engine": "ground classified by the engine from this flight",
    "global": "global elevation model (e.g. Copernicus GLO-30)",
    "estimated": "estimated by Dīvi from the lowest points of this flight",
}
# the error of each source where it is good (1 sigma, metres): assumptions from the literature
BASE_SIGMA_M = {
    "lidar": 0.15,
    "leaf-off": 0.3,
    "survey": 0.3,
    "engine": 0.3,
    "global": 2.0,  # GLO-30: < 4 m (90 %) absolute; less after matching it to this flight
    "estimated": 0.5,
}
GROWTH_M_PER_M = 0.03  # ground guessed from this flight: error grows with distance to seen ground
MAX_SIGMA_M = 6.0
SEEN_TOLERANCE_M = 0.5  # surface this close to the ground: the ground was seen there
CLOSED_CANOPY_SEEN_PCT = 10.0
MIN_ALIGN_CELLS = 30


@dataclass(frozen=True)
class GroundChoice:
    kind: str
    rank: int  # 1 = best
    ranking: tuple[str, ...]  # the available kinds, best first (the first one was used)
    shift_m: float  # added to an outside model to meet this flight (0 for this flight's own)
    aligned_on_cells: int  # how many seen-ground cells the shift was measured on
    seen_pct: float  # share of the area where this flight saw the ground
    note: str


def rank(available: list[str], seen_pct: float) -> list[str]:
    """The available kinds, best first. Under a closed canopy a global model beats the
    flight's own guesses."""
    order = list(KINDS)
    if seen_pct < CLOSED_CANOPY_SEEN_PCT:
        order.remove("global")
        order.insert(order.index("engine"), "global")
    unknown = [k for k in available if k not in KINDS]
    if unknown:
        raise ValueError(f"unknown ground model kind(s): {', '.join(unknown)}")
    return [k for k in order if k in available]


def seen_ground(dsm: FloatArray, ground: FloatArray) -> BoolArray:
    """Cells where the surface is the ground: the ground was seen there."""
    with np.errstate(invalid="ignore"):
        return np.abs(dsm - ground) <= SEEN_TOLERANCE_M


def align(outside: FloatArray, dsm: FloatArray, seen: BoolArray) -> tuple[FloatArray, float, int]:
    """``outside`` moved up or down to meet the surface where the ground was seen (median of the
    differences: robust to a few cars or bushes)."""
    both = seen & np.isfinite(outside) & np.isfinite(dsm)
    n = int(both.sum())
    if n < MIN_ALIGN_CELLS:
        return outside, 0.0, n
    shift = float(np.median(dsm[both] - outside[both]))
    return outside + shift, shift, n


def distance_to_seen(seen: BoolArray, cell_m: float) -> FloatArray:
    """Metres from each cell to the nearest cell where the ground was seen."""
    if not seen.any():
        return np.full(seen.shape, np.inf)
    return np.asarray(ndi.distance_transform_edt(~seen), dtype=float) * cell_m


def ground_sigma(kind: str, distance_m: FloatArray) -> FloatArray:
    """The ground's uncertainty (1 sigma, m) at each cell for a source ``kind``."""
    base = BASE_SIGMA_M[kind]
    if kind in ("lidar", "leaf-off", "survey", "global"):
        return np.full(distance_m.shape, base)
    with np.errstate(invalid="ignore"):
        return np.minimum(base + GROWTH_M_PER_M * distance_m, MAX_SIGMA_M)


def describe_choice(choice: GroundChoice) -> str:
    text = f"ground: {KIND_TEXT[choice.kind]} (rank {choice.rank} of {len(KINDS)})"
    if choice.kind in OUTSIDE_KINDS:
        if choice.aligned_on_cells >= MIN_ALIGN_CELLS:
            text += f", moved {choice.shift_m:+.2f} m to meet this flight"
        else:
            text += ", not matched to this flight (too little open ground): check its datum"
    return text
