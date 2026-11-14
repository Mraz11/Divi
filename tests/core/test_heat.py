# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Relative heat exposure: shadows, sky view, albedo and the ranking, on surfaces worked by hand."""

import numpy as np
import pytest

from avispria.core.heat import (
    ALBEDO_RANGE,
    VEGETATION_ALBEDO,
    brightness,
    coarse,
    fine,
    heat_parts,
    ranked,
    sky_view,
    summary,
    sun_hours,
)

NOON = [(60.0, 180.0)]  # high sun in the south


def flat(n: int = 40) -> np.ndarray:
    return np.zeros((n, n))


def test_a_wall_shades_the_side_away_from_the_sun() -> None:
    surface = flat()
    surface[20, :] = 10.0  # an east-west wall, 10 m high
    hours = sun_hours(surface, 1.0, NOON)
    assert hours[21:26, 5].max() == 1.0  # south of the wall: in sun
    assert hours[15:20, 5].max() == 0.0  # just north: in its shadow (10 m / tan 60 = 5.8 m)
    assert hours[5, 5] == 1.0  # far north: out of the shadow
    assert np.all(sun_hours(surface, 1.0, [(-5.0, 180.0)]) == 0.0)  # night
    surface[0, 0] = np.nan
    assert np.isnan(sun_hours(surface, 1.0, NOON)[0, 0])


def test_open_ground_sees_the_whole_sky_and_a_pit_does_not() -> None:
    assert np.allclose(sky_view(flat(), 1.0, radius_m=10), 1.0)
    pit = np.full((41, 41), 10.0)
    pit[15:26, 15:26] = 0.0  # a 10 m deep, 11 m wide pit
    view = sky_view(pit, 1.0, radius_m=15)
    assert view[20, 20] < 0.5 < view[2, 2]
    with pytest.raises(ValueError, match="positive"):
        sky_view(pit, 0.0)


def test_brightness_is_relative_within_the_flight() -> None:
    rgb = np.stack([np.linspace(0, 255, 100).reshape(10, 10)] * 3, axis=-1)
    b = brightness(rgb)
    assert b.min() == 0.0 and b.max() == 1.0
    assert np.allclose(brightness(rgb * 0.5), b)  # a darker exposure gives the same ranks
    assert np.isnan(brightness(np.full((2, 2, 3), np.nan))).all()


def test_dark_sunlit_paving_ranks_above_green_and_shade() -> None:
    surface = flat(30)
    surface[10, :] = 15.0  # a wall shading the strip north of it
    rgb = np.full((30, 30, 3), 200.0)
    rgb[20:, :15] = 30.0  # dark paving, in the sun (south of the wall)
    green = np.zeros((30, 30), dtype=bool)
    green[20:, 15:] = True  # sunlit lawn beside it
    rgb[20:, 15:] = (40.0, 120.0, 40.0)
    parts = heat_parts(surface, rgb, green, 1.0, [*NOON, (45.0, 150.0), (45.0, 210.0)])
    paving, lawn, shade = parts.index[25, 5], parts.index[25, 25], parts.index[5, 5]
    assert paving > lawn and paving > shade
    assert parts.albedo[25, 25] == VEGETATION_ALBEDO
    assert ALBEDO_RANGE[0] <= parts.albedo[25, 5] < parts.albedo[15, 5] <= ALBEDO_RANGE[1]
    assert parts.hours_used == 3 and np.nanmax(parts.index) == 1.0
    found = summary(parts)
    assert found["index_mean_green"] < found["index_mean_not_green"]


def test_coarse_and_fine_grids_and_ranks() -> None:
    values = np.arange(16.0).reshape(4, 4)
    values[0, 0] = np.nan
    small = coarse(values, 2)
    assert small.shape == (2, 2) and small[0, 0] == pytest.approx((1 + 4 + 5) / 3)
    assert coarse(values, 1) is values and fine(small, 1, (2, 2)) is small
    assert fine(small, 2, (3, 3)).shape == (3, 3)
    odd = coarse(np.ones((5, 5)), 2)
    assert odd.shape == (3, 3) and odd[2, 2] == 1.0
    r = ranked(np.array([[3.0, 1.0], [np.nan, 2.0]]))
    assert r[0, 1] == 0.0 and r[0, 0] == 1.0 and np.isnan(r[1, 0])
    assert np.isnan(ranked(np.full((2, 2), np.nan))).all()
