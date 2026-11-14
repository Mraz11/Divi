# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dīvi's analysis engine: one pass from height and colour to land cover, objects and the
numbers a forester, a farmer or a town planner asks for.

    height above ground ─┬─ roughness ─┐
    colour (excess green, CIE Lab) ────┼─ land cover + confidence (landcover.py)
    shadow predicted from the 3D model ┘        │
       and the sun at photo time (shade.py)     ├─ crowns of trees (crowns.py)
                                                ├─ buildings, roofs, rooftop green (buildings.py)
                                                ├─ roads and street trees (roads.py)
                                                └─ cover, green, 30/300 rules, street shade

Nothing here reads or writes files: ``app/surface_workflow.py`` does that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage as ndi

from avispria.core.buildings import Building, describe_buildings
from avispria.core.crowns import CrownReport, analyse_crowns, local_spread
from avispria.core.landcover import (
    BUILDING,
    GRASS,
    LOW_OBJECT,
    PAVED,
    ROOF_GREEN,
    SHRUB,
    TREE,
    LandCover,
    classify,
)
from avispria.core.profiles import Profile
from avispria.core.roads import RoadReport, find_roads
from avispria.core.safety import Issue
from avispria.core.shade import shaded_share, shadow_mask

FloatArray = NDArray[np.float64]
GREEN_SPACE_M2 = 5000.0  # 0.5 ha: the smallest green space counted for the 300 m rule
GREEN_SPACE_REACH_M = 300.0
CANOPY_TARGET_PCT = 30.0
LOW_CONFIDENCE = 60
LOW_SUN_DEG = 25.0  # as in sun.py: below this colours and shadows mislead


@dataclass(frozen=True)
class SurfaceResult:
    cover: LandCover
    crowns: CrownReport
    buildings: list[Building]
    roads: RoadReport | None
    shadow: NDArray[np.bool_] | None  # predicted at photo time
    metrics: dict[str, Any]
    issues: list[Issue] = field(default_factory=list)


def analyse_surface(
    height: FloatArray,
    cell_m: float,
    prof: Profile,
    *,
    dsm: FloatArray | None = None,
    rgb: FloatArray | None = None,
    sun: tuple[float, float] | None = None,
    shade_at: tuple[float, float] | None = None,
    ground_estimated: bool = False,
    tree_boxes: list[tuple[int, int, int, int]] | None = None,
) -> SurfaceResult:
    """``height`` above ground and optional ``dsm``/``rgb`` on one north-up grid of ``cell_m``.
    ``sun`` is (elevation, azimuth) at photo time; ``shade_at`` the sun to compute street shade
    for (for example 14:00 on a summer day)."""
    shadow = None
    if sun is not None and dsm is not None:
        shadow = shadow_mask(dsm, cell_m, *sun)
    low_sun = sun is not None and sun[0] < LOW_SUN_DEG
    cover = classify(height, cell_m, prof, rgb, shadow, ground_estimated, 0.7 if low_sun else 1.0)
    h = np.nan_to_num(height)
    trees_only = np.where(cover.buildings > 0, 0.0, np.where(np.isnan(height), np.nan, h))
    crowns = analyse_crowns(trees_only, cell_m, rgb, None if sun is None else sun[0], tree_boxes)
    smooth = local_spread(h, cell_m) < prof.flat_spread_m
    buildings = describe_buildings(cover, height, cell_m, smooth) if prof.buildings else []
    roads = find_roads(cover, cell_m, crowns.crowns) if prof.roads else None
    street_shade = None
    if shade_at is not None and roads is not None and roads.roads:
        tree_surface = np.where(cover.classes == TREE, h, 0.0)
        mask = shadow_mask(tree_surface, cell_m, *shade_at)
        street_shade = round(shaded_share(mask, roads.labels > 0) * 100, 1)
    metrics = _metrics(cover, crowns, buildings, roads, cell_m, street_shade)
    issues: list[Issue] = []
    if metrics["confidence_mean"] < LOW_CONFIDENCE:
        issues.append(
            Issue(
                "warning",
                "LC001",
                f"the land cover is uncertain over much of the map (mean confidence "
                f"{metrics['confidence_mean']:.0f} of 100): shadows, an estimated ground or "
                "heights close to the class limits; check it against the orthophoto",
            )
        )
    issues.extend(crowns.issues)
    return SurfaceResult(cover, crowns, buildings, roads, shadow, metrics, issues)


def _metrics(
    cover: LandCover,
    crowns: CrownReport,
    buildings: list[Building],
    roads: RoadReport | None,
    cell_m: float,
    street_shade: float | None,
) -> dict[str, Any]:
    cls = cover.classes
    valid = cls != 0
    n = max(1, int(np.count_nonzero(valid)))

    def pct(*codes: int) -> float:
        return round(float(np.isin(cls, codes).sum()) / n * 100.0, 1)

    roof_area = sum(b.area_m2 for b in buildings)
    roof_green = sum(b.green_m2 for b in buildings)
    canopy = pct(TREE)
    out: dict[str, Any] = {
        "area_m2": round(n * cell_m * cell_m, 1),
        "cover_pct": cover.shares(),
        "tree_canopy_pct": canopy,
        "green_pct": pct(GRASS, SHRUB, TREE, ROOF_GREEN),
        "impervious_pct": pct(PAVED, BUILDING, LOW_OBJECT),
        "trees": crowns.trees,
        "dieback_candidates": crowns.dieback_candidates,
        "buildings": len(buildings),
        "built_area_m2": round(roof_area, 1),
        "building_height_median_m": (
            round(float(np.median([b.height_m for b in buildings])), 1) if buildings else None
        ),
        "rooftop_green_m2": round(roof_green, 1),
        "rooftop_green_pct_of_roofs": round(roof_green / roof_area * 100, 1) if roof_area else 0.0,
        "canopy_30_rule_met": canopy >= CANOPY_TARGET_PCT,
        "buildings_near_green_space_pct": _near_green(cover, buildings, cell_m),
        "street_shade_pct": street_shade,
        "confidence_mean": round(float(cover.confidence[valid].mean()), 1) if valid.any() else 0.0,
    }
    if roads is not None:
        length = sum(r.length_m for r in roads.roads)
        street = sum(r.street_trees for r in roads.roads)
        out |= {
            "roads": len(roads.roads),
            "road_length_m": round(length, 1),
            "paved_not_road_m2": roads.paved_other_m2,
            "street_trees": street,
            "street_trees_per_100m": round(street / length * 100, 1) if length else 0.0,
            "street_tree_gaps": sum(r.gaps for r in roads.roads),
        }
    return out


def _near_green(cover: LandCover, buildings: list[Building], cell_m: float) -> float | None:
    """Share of buildings within 300 m of a green space of at least 0.5 ha (the '300' of the
    3-30-300 rule), or None when the map holds no such green space or no building. A map smaller
    than 300 m can only show what lies inside it."""
    if not buildings:
        return None
    green = np.isin(cover.classes, (GRASS, SHRUB, TREE))
    labels, n = ndi.label(green)
    if n == 0:
        return None
    sizes = ndi.sum(np.ones_like(labels), labels, np.arange(1, n + 1)) * cell_m * cell_m
    big = np.isin(labels, np.flatnonzero(sizes >= GREEN_SPACE_M2) + 1)
    if not big.any():
        return None
    reach = ndi.distance_transform_edt(~big) * cell_m
    near = [reach[round(b.row), round(b.col)] <= GREEN_SPACE_REACH_M for b in buildings]
    return round(float(sum(near)) / len(near) * 100, 1)
