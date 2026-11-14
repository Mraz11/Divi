# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Land cover from height above ground, surface roughness, colour and predicted shadow.

The same rules serve forest, farm and town; a ``Profile`` sets the thresholds. Rules, in order:

1. Height above ground splits ground level, low objects and raised surfaces.
2. Raised, smooth and not green surfaces, closed and hole-filled into blocks of at least
   ``building_min_m2``, are buildings; everything raised inside a building is roof, or rooftop
   vegetation where it is green.
3. Other raised cells: green = tree canopy, not green = other tall (dead crowns, masts, clutter).
4. Low objects: green = shrub, not green = car, wall, stack.
5. Ground level: green = grass or crop; dark, smooth, bluish and not in shadow = water; warm
   brown = bare soil; the rest (grey) = paved.

Every cell also gets a confidence (0-100). It drops where the decision rests on colour inside a
predicted shadow, where the height is within 0.3 m of a threshold, where the ground was estimated
rather than modelled, and for green surfaces lying flat on a roof (paint or shade cloth look the
same as a lawn from above).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi

from avispria.core.crowns import local_spread, srgb_to_lab
from avispria.core.profiles import Profile

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

NO_DATA, PAVED, SOIL, GRASS, WATER = 0, 1, 2, 3, 4
LOW_OBJECT, SHRUB, TREE, BUILDING, ROOF_GREEN, TALL_OTHER, GROUND = 5, 6, 7, 8, 9, 10, 11
CLASSES: dict[int, tuple[str, tuple[int, int, int]]] = {
    NO_DATA: ("no data", (0, 0, 0)),
    PAVED: ("paved (roads, yards)", (150, 150, 150)),
    SOIL: ("bare soil", (176, 132, 82)),
    GRASS: ("grass, crops, low plants", (160, 210, 110)),
    WATER: ("water", (60, 110, 200)),
    LOW_OBJECT: ("low objects (cars, walls)", (230, 200, 60)),
    SHRUB: ("shrubs", (90, 170, 70)),
    TREE: ("tree canopy", (25, 110, 40)),
    BUILDING: ("buildings (roofs)", (200, 70, 60)),
    ROOF_GREEN: ("rooftop vegetation", (120, 230, 170)),
    TALL_OTHER: ("other tall (dead crowns, masts)", (130, 60, 140)),
    GROUND: ("ground (colour unknown)", (200, 200, 170)),
}
THRESHOLD_BAND_M = 0.3


@dataclass(frozen=True)
class LandCover:
    classes: NDArray[np.uint8]
    confidence: NDArray[np.uint8]  # 0-100
    buildings: NDArray[np.int32]  # building id per cell, 0 = none
    green: BoolArray | None  # None without colour

    def shares(self) -> dict[str, float]:
        """Percentage of the mapped area per class (classes with data only)."""
        valid = self.classes != NO_DATA
        n = int(np.count_nonzero(valid))
        if n == 0:
            return {}
        counts = np.bincount(self.classes[valid], minlength=len(CLASSES))
        return {
            CLASSES[k][0]: round(float(counts[k]) / n * 100.0, 1)
            for k in CLASSES
            if k != NO_DATA and counts[k]
        }


def excess_green(rgb: FloatArray) -> FloatArray:
    total = rgb.sum(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        exg = (2 * rgb[..., 1] - rgb[..., 0] - rgb[..., 2]) / total
    return np.asarray(np.where(total > 0, exg, np.nan))


def majority(mask: BoolArray) -> BoolArray:
    """3 x 3 majority vote: removes speckle, keeps straight edges where they are."""
    votes = ndi.uniform_filter(mask.astype(float), size=3, mode="nearest")
    return np.asarray(votes > 0.5)


def disc(radius_cells: int) -> BoolArray:
    r = max(1, radius_cells)
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    return np.asarray(yy * yy + xx * xx <= r * r)


def building_blocks(candidate: BoolArray, cell_m: float, min_m2: float) -> NDArray[np.int32]:
    """Smooth not-green raised cells grown into whole roofs: small gaps (vents, tanks, edges
    blurred by the 3D model) closed, holes filled, small pieces dropped."""
    closed = ndi.binary_closing(candidate, structure=disc(round(1.0 / cell_m)))
    filled = ndi.binary_fill_holes(closed)
    # an opening removes thin strips (a wall top, a fence) but would also round off the corners:
    # keep every piece of the filled mask that still has a core after the opening, whole
    core = ndi.binary_opening(filled, structure=disc(round(0.75 / cell_m)))
    labels, n = ndi.label(filled)
    if n == 0:
        return np.zeros(candidate.shape, dtype=np.int32)
    ids = np.arange(1, n + 1)
    sizes = ndi.sum(np.ones_like(labels), labels, ids) * cell_m * cell_m
    has_core = ndi.maximum(core, labels, ids) > 0
    keep = np.flatnonzero((sizes >= min_m2) & has_core) + 1
    lookup = np.zeros(n + 1, dtype=np.int32)
    lookup[keep] = np.arange(1, keep.size + 1, dtype=np.int32)
    return np.asarray(lookup[labels], dtype=np.int32)


def grow_into(labels: NDArray[np.int32], allowed: BoolArray, cells: int) -> NDArray[np.int32]:
    """Grow each labelled piece by up to ``cells`` into ``allowed`` unlabelled cells: the rough
    rim of a roof (where the wall drops away) belongs to the building too."""
    out = labels.copy()
    for _ in range(cells):
        grown = ndi.grey_dilation(out, size=3)
        take = (out == 0) & allowed & (grown > 0)
        if not take.any():
            break
        out[take] = grown[take]
    return out


def classify(
    height: FloatArray,
    cell_m: float,
    prof: Profile,
    rgb: FloatArray | None = None,
    shadow: BoolArray | None = None,
    ground_estimated: bool = False,
    colour_trust: float = 1.0,
) -> LandCover:
    """Land cover per cell; ``height`` is above ground (NaN = no data), ``rgb`` 8-bit, rows x
    cols x 3, on the same grid. ``colour_trust`` (0-1) scales the confidence of every decision
    made on colour: below 1 when the light itself was poor (low sun turns everything orange)."""
    if cell_m <= 0:
        raise ValueError("cell_m must be positive")
    valid = ~np.isnan(height)
    h = np.where(valid, height, 0.0)
    spread = local_spread(h, cell_m)
    smooth = spread < prof.flat_spread_m
    shade = np.zeros(h.shape, dtype=bool) if shadow is None else shadow & valid
    low = h < prof.low_m
    raised = h >= prof.raised_m
    middle = ~low & ~raised
    cls = np.full(h.shape, NO_DATA, dtype=np.uint8)
    conf = np.full(h.shape, 0.9)
    green: BoolArray | None = None
    if rgb is not None:
        exg = np.nan_to_num(excess_green(rgb), nan=0.0)
        green = majority(exg > prof.green_threshold)  # pixel noise is not colour
        lab = srgb_to_lab(ndi.uniform_filter(rgb, size=(3, 3, 1), mode="nearest"))
        lightness, a_star, b_star = lab[..., 0], lab[..., 1], lab[..., 2]
    candidate = raised & smooth & valid & (np.ones_like(raised) if green is None else ~green)
    buildings = (
        building_blocks(candidate, cell_m, prof.building_min_m2)
        if prof.buildings
        else np.zeros(h.shape, dtype=np.int32)
    )
    buildings = grow_into(buildings, raised & valid, max(1, round(1.0 / cell_m)))
    on_roof = (buildings > 0) & ~low
    if green is None:
        cls[raised] = np.where(smooth[raised], TALL_OTHER, TREE)
        cls[middle] = LOW_OBJECT
        cls[low] = GROUND
        cls[on_roof] = BUILDING
    else:
        cls[raised] = np.where(green[raised], TREE, TALL_OTHER)
        cls[middle] = np.where(green[middle], SHRUB, LOW_OBJECT)
        water = ~shade & smooth & (lightness < 35) & (b_star < 0) & (np.abs(a_star) < 15)
        soil = (a_star > 3) & (b_star > 12)
        ground = np.where(green, GRASS, np.where(water, WATER, np.where(soil, SOIL, PAVED)))
        cls[low] = ground[low]
        inner_roof = on_roof & ndi.binary_erosion(buildings > 0)  # the rim borders the ground
        cls[on_roof] = np.where((green & inner_roof)[on_roof], ROOF_GREEN, BUILDING)
        conf = conf * colour_trust
        conf = np.where(shade, conf * 0.6, conf)  # colour decided in shade
        conf = np.where(on_roof & green & smooth, conf * 0.6, conf)  # paint or cloth?
    near = np.zeros(h.shape, dtype=bool)
    for threshold in (prof.low_m, prof.raised_m):
        near |= np.abs(h - threshold) < THRESHOLD_BAND_M
    conf = np.where(near, conf * 0.7, conf)
    if ground_estimated:
        conf = conf * 0.85
    cls[~valid] = NO_DATA
    confidence = np.where(valid, np.round(conf * 100), 0).astype(np.uint8)
    return LandCover(cls, confidence, np.where(valid, buildings, 0).astype(np.int32), green)
