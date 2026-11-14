# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Roads and the trees along them.

Roads: paved ground (cars and their shadows on it included) in pieces that are long and narrow.
For each piece the distance to its edge is computed; its ridge is the centre line, twice the ridge
distance is the width, and area / width is the length. Pieces at least ROAD_ELONGATION times
longer than wide, 2 to 40 m wide, are roads; wide paved pieces are yards and car parks.

Street trees: crowns whose top lies within ``STREET_BUFFER_M`` of a road. Along each road they are
put in order on the road's main direction; spacing is the distance between neighbours, and a gap
is a spacing more than 1.5x the road's median spacing (a missing tree in a planted row).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi

from avispria.core.crowns import Crown
from avispria.core.landcover import LOW_OBJECT, PAVED, LandCover, disc

ROAD_ELONGATION = 3.0
ROAD_WIDTH_M = (2.0, 40.0)
ROAD_MIN_M2 = 40.0
STREET_BUFFER_M = 8.0
GAP_FACTOR = 1.5  # one missing tree doubles the spacing; noise stays well below 1.5x


@dataclass(frozen=True)
class Road:
    id: int
    width_m: float
    length_m: float
    area_m2: float
    street_trees: int
    spacing_m: float | None  # median distance between neighbouring street trees
    gaps: int  # spacings over 1.5x the median: missing trees
    tree_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class RoadReport:
    roads: list[Road]
    labels: NDArray[np.int32]  # road id per cell
    paved_other_m2: float  # paved ground that is not road (yards, car parks)
    street_tree_ids: frozenset[int]


def road_pieces(cover: LandCover, cell_m: float) -> tuple[NDArray[np.int32], int]:
    paved = cover.classes == PAVED
    vehicles = (cover.classes == LOW_OBJECT) & ndi.binary_dilation(paved, structure=disc(2))
    surface = ndi.binary_closing(paved | vehicles, structure=disc(round(1.0 / cell_m)))
    surface = ndi.binary_opening(surface, structure=disc(round(0.75 / cell_m)))
    labels, n = ndi.label(surface)
    return labels.astype(np.int32), int(n)


def _order_along(cells: NDArray[np.float64], points: NDArray[np.float64]) -> NDArray[np.float64]:
    """Positions of ``points`` (row, col) along the main direction of ``cells``."""
    centre = cells.mean(axis=0)
    _, _, axes = np.linalg.svd(cells - centre, full_matrices=False)
    return np.asarray((points - centre) @ axes[0])


def find_roads(cover: LandCover, cell_m: float, crowns: list[Crown] | None = None) -> RoadReport:
    labels, n = road_pieces(cover, cell_m)
    out = np.zeros(labels.shape, dtype=np.int32)
    roads: list[Road] = []
    distance = ndi.distance_transform_edt(labels > 0) * cell_m
    ridge = (labels > 0) & (distance >= ndi.maximum_filter(distance, size=3))
    other = 0.0
    kept = 0
    for i in range(1, n + 1):
        piece = labels == i
        area = float(piece.sum()) * cell_m * cell_m
        on_ridge = distance[piece & ridge]
        width = 2.0 * float(np.median(on_ridge)) if on_ridge.size else 0.0
        length = area / width if width > 0 else 0.0
        is_road = (
            area >= ROAD_MIN_M2
            and ROAD_WIDTH_M[0] <= width <= ROAD_WIDTH_M[1]
            and length >= ROAD_ELONGATION * width
        )
        if not is_road:
            other += area
            continue
        kept += 1
        out[piece] = kept
        roads.append(Road(kept, round(width, 1), round(length, 1), round(area, 1), 0, None, 0))
    street: set[int] = set()
    if crowns and roads:
        away = ndi.distance_transform_edt(out == 0) * cell_m
        nearest = ndi.distance_transform_edt(out == 0, return_distances=False, return_indices=True)
        by_road: dict[int, list[Crown]] = {}
        n_rows, n_cols = int(np.size(out, 0)), int(np.size(out, 1))
        for c in crowns:
            r, k = round(c.row), round(c.col)
            if 0 <= r < n_rows and 0 <= k < n_cols and away[r, k] <= STREET_BUFFER_M:
                road = int(out[nearest[0][r, k], nearest[1][r, k]])
                by_road.setdefault(road, []).append(c)
                street.add(c.id)
        roads = [_with_trees(road, by_road.get(road.id, []), out, cell_m) for road in roads]
    return RoadReport(roads, out, round(other, 1), frozenset(street))


def _with_trees(road: Road, trees: list[Crown], labels: NDArray[np.int32], cell_m: float) -> Road:
    if not trees:
        return road
    cells = np.argwhere(labels == road.id).astype(float)
    tops = np.array([[c.row, c.col] for c in trees])
    order = np.sort(_order_along(cells, tops)) * cell_m
    gaps_between = np.diff(order)
    spacing = float(np.median(gaps_between)) if gaps_between.size else None
    gaps = int(np.sum(gaps_between > GAP_FACTOR * spacing)) if spacing else 0
    return Road(
        road.id,
        road.width_m,
        road.length_m,
        road.area_m2,
        len(trees),
        None if spacing is None else round(spacing, 1),
        gaps,
        sorted(c.id for c in trees),
    )
