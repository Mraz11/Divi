# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The analysis engine on a synthetic town with a known answer for every cell."""

import numpy as np
import pytest

from avispria.core import landcover as lc
from avispria.core.profiles import PROFILES, profile
from avispria.core.surface import analyse_surface
from cityscene import CELL, city, interior

URBAN = PROFILES["urban"]


@pytest.fixture(scope="module", params=[7, 8, 9])
def town(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    s = city(request.param)
    r = analyse_surface(
        s.height, CELL, URBAN, dsm=s.dsm, rgb=s.rgb, sun=(50.0, 170.0), shade_at=(60.0, 230.0)
    )
    return s, r


def test_every_class_is_right_inside_and_almost_everywhere(town) -> None:  # type: ignore[no-untyped-def]
    s, r = town
    for code in lc.CLASSES:
        inside = interior(s.truth == code)
        if inside.any():
            right = float((r.cover.classes[inside] == code).mean())
            assert right >= 0.94, (lc.CLASSES[code][0], right)
    assert float((r.cover.classes == s.truth).mean()) >= 0.98  # edges included


def test_buildings_heights_roofs_and_rooftop_garden(town) -> None:  # type: ignore[no-untyped-def]
    _, r = town
    flat, pitched = sorted(r.buildings, key=lambda b: b.col)
    assert flat.area_m2 == pytest.approx(24 * 16, rel=0.03)
    assert flat.height_m == pytest.approx(9.0, abs=0.1) and flat.floors == 3
    assert flat.roof == "flat" and flat.green_m2 == pytest.approx(36, rel=0.12)
    assert pitched.area_m2 == pytest.approx(14 * 12, rel=0.03)
    assert pitched.roof == "pitched" and pitched.roof_slope_deg == pytest.approx(18.4, abs=1.5)
    assert pitched.green_m2 == 0.0


def test_road_street_trees_and_the_missing_tree(town) -> None:  # type: ignore[no-untyped-def]
    _, r = town
    (road,) = r.roads.roads
    assert road.width_m == pytest.approx(8.0, abs=0.6)
    assert road.length_m == pytest.approx(100, abs=6)
    assert road.street_trees == 5 and road.spacing_m == pytest.approx(15, abs=1)
    assert road.gaps == 1  # the tree at 55 m is missing
    assert r.roads.paved_other_m2 > 600  # the yard is paved but not road


def test_town_numbers(town) -> None:  # type: ignore[no-untyped-def]
    _, r = town
    m = r.metrics
    assert m["trees"] == 7 and m["dieback_candidates"] == 0
    assert m["buildings"] == 2 and m["street_trees"] == 5 and m["street_tree_gaps"] == 1
    assert m["rooftop_green_pct_of_roofs"] == pytest.approx(36 / 552 * 100, abs=1.5)
    assert m["canopy_30_rule_met"] is False and m["tree_canopy_pct"] < 10
    assert m["green_pct"] + m["impervious_pct"] <= 100.0
    assert m["buildings_near_green_space_pct"] is None  # road and houses cut the grass small
    assert 0.0 <= m["street_shade_pct"] <= 100.0
    assert r.issues == []


def test_without_colour_or_sun_it_still_finds_heights_and_buildings() -> None:
    s = city()
    r = analyse_surface(s.height, CELL, URBAN)
    assert r.shadow is None and len(r.buildings) == 2
    assert lc.GROUND in r.cover.classes and lc.GRASS not in r.cover.classes
    assert r.metrics["street_shade_pct"] is None


def test_profiles_change_what_is_extracted() -> None:
    s = city()
    forest = analyse_surface(s.height, CELL, profile("forest"), rgb=s.rgb)
    assert forest.roads is None and "roads" not in forest.metrics
    farm = analyse_surface(s.height, CELL, profile("farm"), rgb=s.rgb)
    assert farm.roads is not None
    with pytest.raises(ValueError, match="unknown profile"):
        profile("ocean")


def test_low_confidence_is_reported() -> None:
    s = city()
    shaded = analyse_surface(
        s.height, CELL, URBAN, dsm=s.dsm, rgb=s.rgb, sun=(3.0, 250.0), ground_estimated=True
    )
    assert shaded.shadow is not None and shaded.shadow.mean() > 0.3
    assert "LC001" in [i.code for i in shaded.issues]
    assert "CH003" in [i.code for i in shaded.issues]  # colour of crowns at low sun


def test_the_300_m_rule_with_a_park() -> None:
    height = np.zeros((400, 400))  # 200 m x 200 m of grass at 0.5 m
    height[10:30, 10:30] = 6.0  # a house near the park
    height[380:398, 380:398] = 6.0  # and one on the far side, still within 300 m
    rgb = np.zeros((400, 400, 3))
    rgb[:] = (100, 160, 70)
    rgb[height > 0] = (180, 180, 180)
    r = analyse_surface(height, 0.5, URBAN, rgb=rgb)
    assert r.metrics["buildings"] == 2 and r.metrics["buildings_near_green_space_pct"] == 100.0
    assert (
        analyse_surface(height * 0, 0.5, URBAN, rgb=rgb).metrics["buildings_near_green_space_pct"]
        is None
    )  # no building


def test_bad_grid() -> None:
    with pytest.raises(ValueError):
        lc.classify(np.zeros((5, 5)), 0.0, URBAN)
    empty = lc.classify(np.full((5, 5), np.nan), 0.5, URBAN)
    assert empty.shares() == {} and int(empty.confidence.max()) == 0
