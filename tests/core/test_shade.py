# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shadows of a block of known height under a known sun."""

import math

import numpy as np
import pytest

from avispria.core.shade import shaded_share, shadow_mask


def block(height: float = 10.0) -> np.ndarray:
    z = np.zeros((101, 101))
    z[45:55, 45:55] = height  # a 10 x 10 cell block in the middle
    return z


@pytest.mark.parametrize("elevation", [45.0, 30.0, 60.0])
def test_shadow_length_follows_the_sun(elevation: float) -> None:
    sun_south = shadow_mask(block(), 1.0, elevation, 180.0)  # sun in the south: shadow north
    length = 10.0 / math.tan(math.radians(elevation))
    column = sun_south[:45, 50]
    assert int(column.sum()) == pytest.approx(length, abs=1.0)
    assert not sun_south[55:, 50].any()  # nothing on the sunny side
    assert not sun_south[50, :45].any() and not sun_south[50, 55:].any()


def test_east_sun_shades_the_west_and_the_horizon_shades_everything() -> None:
    east = shadow_mask(block(), 1.0, 45.0, 90.0)
    assert east[50, 40] and not east[50, 60]
    z = block()
    z[0, 0] = np.nan
    down = shadow_mask(z, 1.0, -1.0, 180.0)
    assert down.sum() == z.size - 1 and not down[0, 0]


def test_the_roof_itself_is_lit_and_flat_ground_has_no_shadow() -> None:
    m = shadow_mask(block(), 1.0, 45.0, 180.0)
    assert not m[45:55, 45:55].any()
    assert not shadow_mask(np.zeros((20, 20)), 0.5, 10.0, 200.0).any()
    assert shaded_share(m, np.ones_like(m)) == pytest.approx(m.mean())
    assert shaded_share(m, np.zeros_like(m)) == 0.0
    with pytest.raises(ValueError):
        shadow_mask(block(), 0.0, 45, 180)
