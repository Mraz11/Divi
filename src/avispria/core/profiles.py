# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What was mapped: forest, farm or town. One engine, three sets of thresholds.

Every analysis in Dīvi starts from the same layers (height above ground, surface roughness,
colour, predicted shadow); a profile only says where the class boundaries lie and which objects
are worth extracting. Values are documented next to each field so they can be argued with.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProfileName = Literal["forest", "farm", "urban"]


@dataclass(frozen=True)
class Profile:
    name: ProfileName
    title: str
    ground_window_m: float  # wider than the widest object with no ground in it
    low_m: float  # below: ground level (grass, crops, paving, soil, water)
    raised_m: float  # at or above: trees and buildings; between: shrubs, cars, walls
    green_threshold: float  # excess green (2g-r-b)/(r+g+b) above this is green vegetation
    flat_spread_m: float  # height spread within 1.5 m below this is a smooth (built) surface
    building_min_m2: float  # smaller smooth raised patches are not buildings
    roads: bool  # extract roads and street trees
    buildings: bool  # extract buildings and rooftop greenery


PROFILES: dict[ProfileName, Profile] = {
    "forest": Profile(
        name="forest",
        title="Forest or plantation",
        ground_window_m=80.0,  # the widest closed stand without a gap
        low_m=0.5,
        raised_m=2.0,  # trees from 2 m, the canopy cover convention used by canopy.py
        green_threshold=0.02,
        flat_spread_m=0.15,
        building_min_m2=10.0,
        roads=False,
        buildings=True,  # forest stations, sheds: found so they are not counted as trees
    ),
    "farm": Profile(
        name="farm",
        title="Farm, crops or orchard",
        ground_window_m=40.0,  # fields are open: a narrower window follows the terrain closely
        low_m=0.3,  # crops of a few decimetres are already above ground level
        raised_m=2.0,
        green_threshold=0.02,
        flat_spread_m=0.15,
        building_min_m2=10.0,
        roads=True,  # farm tracks
        buildings=True,
    ),
    "urban": Profile(
        name="urban",
        title="Town or city",
        ground_window_m=100.0,  # wider than the largest building block
        low_m=0.5,
        raised_m=2.5,  # walls and parked vans stay below
        green_threshold=0.02,
        flat_spread_m=0.15,
        building_min_m2=12.0,  # a small room or kiosk
        roads=True,
        buildings=True,
    ),
}


def profile(name: str) -> Profile:
    try:
        return PROFILES[name]  # type: ignore[index]
    except KeyError:
        raise ValueError(f"unknown profile {name!r}: choose {', '.join(PROFILES)}") from None
