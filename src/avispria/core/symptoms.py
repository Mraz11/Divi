# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Visible symptoms of disease or stress, per crown and for the whole flight.

What an RGB camera can see from a mapping height: crowns that have lost leaves, turned yellow,
brown or red, or died back: symptoms already visible to a person standing below. What it cannot:
infection before symptoms (latent infection; Bock et al. 2020 state that neither raters nor
visible-light images can detect it), early physiological stress (that needs near-infrared,
thermal or hyperspectral sensors), or single leaf lesions (they need about 0.5 mm per pixel; a
mapping flight gives 1 to 3 cm).

How a crown is judged: against the other crowns of the same flight, never against fixed values
(the camera's colours are not reflectance). For each tree crown: the mean green and red chromatic
coordinates (GCC, RCC), excess red, CIE a* (from the crown analysis) and the share of the crown
that is not green. A crown is a candidate when half of it or more is not green (dieback), or
when its GCC is far below the flight's other crowns (robust z-score <= -2.5: median and MAD, so a
few sick crowns do not hide themselves). Every candidate is a place to check on the ground, with
a standard rating scale, by someone who does not know which crowns were flagged.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi

from avispria.core.indices import exr, gcc, rcc

FloatArray = NDArray[np.float64]
Z_CANDIDATE = -2.5
MIN_CROWNS = 10  # fewer crowns than this: no flight-relative scores
LESION_CELL_M = 0.0005


@dataclass(frozen=True)
class CrownSymptoms:
    crown_id: int
    gcc: float
    rcc: float
    exr: float
    gcc_z: float | None  # robust z-score among this flight's tree crowns
    candidate: bool
    reason: str


@dataclass(frozen=True)
class SymptomReport:
    crowns: list[CrownSymptoms]
    candidates: int
    candidate_area_pct: float  # of the tree crown area: the plot-scale severity
    notes: list[str]


def _robust_z(values: FloatArray) -> FloatArray:
    med = np.median(values)
    mad = 1.4826 * np.median(np.abs(values - med))
    if mad <= 0:
        return np.zeros_like(values)
    return np.asarray((values - med) / mad, dtype=float)


def crown_symptoms(
    labels: NDArray[np.int32],
    rgb: FloatArray,
    tree_ids: list[int],
    dieback_ids: set[int],
    cell_m: float,
    low_sun: bool = False,
) -> SymptomReport:
    """Score the tree crowns ``tree_ids`` (labels in ``labels``) by their colour."""
    ids = np.array(sorted(tree_ids), dtype=np.int64)
    notes = [
        "visible symptoms only: RGB cannot detect latent infection or stress before symptoms",
        f"one cell here is {cell_m * 100:.0f} cm: crown-scale symptoms only (single leaf "
        f"lesions need about {LESION_CELL_M * 1000:.1f} mm per pixel)",
        "scores are relative to the other crowns of this flight; check every candidate on the "
        "ground with a standard rating scale",
    ]
    if low_sun:
        notes.append("the sun was low: colours are unreliable, treat candidates with caution")
    if ids.size == 0:
        return SymptomReport([], 0, 0.0, notes)
    means = {}
    for name, fn in (("gcc", gcc), ("rcc", rcc), ("exr", exr)):
        values = np.nan_to_num(fn(rgb))
        means[name] = np.asarray(ndi.mean(values, labels, ids), dtype=float)
    z = _robust_z(means["gcc"]) if ids.size >= MIN_CROWNS else None
    if z is None:
        notes.append(f"fewer than {MIN_CROWNS} crowns: only dieback (half not green) is scored")
    sizes = np.asarray(ndi.sum(np.ones_like(labels), labels, ids), dtype=float)
    crowns: list[CrownSymptoms] = []
    for k, cid in enumerate(ids):
        zk = None if z is None else float(z[k])
        reasons = []
        if int(cid) in dieback_ids:
            reasons.append("half or more of the crown not green")
        if zk is not None and zk <= Z_CANDIDATE:
            reasons.append(f"much less green than the other crowns (z {zk:.1f})")
        crowns.append(
            CrownSymptoms(
                int(cid),
                round(float(means["gcc"][k]), 4),
                round(float(means["rcc"][k]), 4),
                round(float(means["exr"][k]), 4),
                None if zk is None else round(zk, 2),
                bool(reasons),
                "; ".join(reasons),
            )
        )
    flagged = np.array([c.candidate for c in crowns])
    area = float(sizes[flagged].sum() / sizes.sum() * 100) if sizes.sum() else 0.0
    return SymptomReport(crowns, int(flagged.sum()), round(area, 1), notes)
