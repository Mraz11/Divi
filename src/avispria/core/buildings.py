# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Buildings from the land cover: footprint size, height, floors, roof shape, rooftop greenery.

Height is the median height above ground over the roof (robust to tanks and parapets); floors
are that height over 3 m, a rough figure for South Asian concrete frames (2.9-3.2 m storeys).
Roof slope comes from a least-squares plane: under 5 degrees is flat. Rooftop vegetation is the
green part of the roof; ``green_flat_m2`` is green lying flat on the roof (could be paint or shade
cloth as well as a lawn), reported apart so it is never silently counted as plants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi

from avispria.core.landcover import ROOF_GREEN, LandCover

FloatArray = NDArray[np.float64]
STOREY_M = 3.0
FLAT_ROOF_DEG = 5.0


@dataclass(frozen=True)
class Building:
    id: int
    row: float  # centre, grid cells
    col: float
    area_m2: float
    height_m: float
    max_height_m: float
    floors: int
    roof_slope_deg: float
    roof: str  # "flat" or "pitched"
    green_m2: float  # rooftop vegetation
    green_flat_m2: float  # of which lying flat on the roof (lawn, paint or cloth)
    confidence: int  # mean land-cover confidence over the roof, 0-100


def _slope_deg(surface: FloatArray, roof: NDArray[np.bool_], cell_m: float) -> float:
    """Median slope of the roof faces: works for flat, mono-pitch, gable and hip roofs alike
    (one plane through a gable would average its two faces to zero). Edge cells are left out."""
    inner = ndi.binary_erosion(roof, iterations=2)
    if not inner.any():
        return 0.0
    gy, gx = np.gradient(surface, cell_m)
    return math.degrees(math.atan(float(np.median(np.hypot(gx, gy)[inner]))))


def describe_buildings(
    cover: LandCover, height: FloatArray, cell_m: float, flat_spread: NDArray[np.bool_]
) -> list[Building]:
    """One record per building of ``cover``; ``flat_spread`` marks smooth cells."""
    out: list[Building] = []
    h = np.nan_to_num(height)
    for i, where in enumerate(ndi.find_objects(cover.buildings), start=1):
        if where is None:
            continue
        inside = cover.buildings[where] == i
        z = h[where][inside]
        rr, cc = np.nonzero(inside)
        green = (cover.classes[where] == ROOF_GREEN) & inside
        roof = inside & ~green
        zr = h[where][roof] if roof.any() else z
        slope = _slope_deg(h[where], roof if roof.any() else inside, cell_m)
        height_m = float(np.median(zr))
        cell_area = cell_m * cell_m
        out.append(
            Building(
                id=i,
                row=float(rr.mean() + where[0].start),
                col=float(cc.mean() + where[1].start),
                area_m2=round(float(inside.sum()) * cell_area, 1),
                height_m=round(height_m, 2),
                max_height_m=round(float(z.max()), 2),
                floors=max(1, round(height_m / STOREY_M)),
                roof_slope_deg=round(slope, 1),
                roof="flat" if slope < FLAT_ROOF_DEG else "pitched",
                green_m2=round(float(green.sum()) * cell_area, 1),
                green_flat_m2=round(float((green & flat_spread[where]).sum()) * cell_area, 1),
                confidence=round(float(cover.confidence[where][inside].mean())),
            )
        )
    return out
