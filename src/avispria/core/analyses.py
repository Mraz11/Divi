# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The analyses that can be switched off, so a project measures only what it needs.

Always done, because everything else stands on it: the canopy height model with its quality
checks (ground source, doming, ground uncertainty), and the tree tops and crowns. Everything in
``SWITCHES`` is on unless switched off; switching one off means it is neither computed (where it
can be skipped) nor saved nor reported.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Switch:
    key: str
    title: str
    what: str  # what it makes, in one sentence
    metrics: tuple[str, ...] = ()  # keys of the surface metrics that belong to it


SWITCHES: tuple[Switch, ...] = (
    Switch(
        "landcover",
        "Land cover map",
        "Classes such as paved, bare soil, grass, shrubs, tree canopy and roofs, with a "
        "confidence map.",
        ("cover_pct", "green_pct", "impervious_pct", "confidence_mean"),
    ),
    Switch(
        "buildings",
        "Buildings and rooftop green",
        "Building outlines, heights and green roofs. Buildings are kept out of the tree counts "
        "either way.",
        (
            "buildings",
            "built_area_m2",
            "building_height_median_m",
            "rooftop_green_m2",
            "rooftop_green_pct_of_roofs",
        ),
    ),
    Switch(
        "roads",
        "Roads and street trees",
        "Road outlines, length, street trees per 100 m and gaps in the rows.",
        (
            "roads",
            "road_length_m",
            "paved_not_road_m2",
            "street_trees",
            "street_trees_per_100m",
            "street_tree_gaps",
        ),
    ),
    Switch(
        "street_shade",
        "Street shade",
        "Share of the roads shaded by trees at 14:00 on a summer day. Needs roads.",
        ("street_shade_pct",),
    ),
    Switch(
        "rule_3_30_300",
        "3-30-300 checks",
        "Whether canopy cover reaches 30 %, and the share of buildings within 300 m of a green "
        "space.",
        ("canopy_30_rule_met", "buildings_near_green_space_pct"),
    ),
    Switch(
        "heat",
        "Heat exposure (relative)",
        "Which surfaces gain the most heat by day, from sun hours, darkness and greenness, ranked "
        "within this flight; not temperature. Needs the photos' times.",
    ),
    Switch(
        "biomass",
        "Biomass and carbon",
        "Above-ground biomass, carbon and CO2 equivalent per tree and in total, with 95 % ranges.",
    ),
    Switch(
        "indices",
        "Colour index bands",
        "Eleven vegetation index rasters, relative within this flight, and a vegetation mask.",
    ),
    Switch(
        "symptoms",
        "Visible symptom flags",
        "Crowns that look less green than the rest of this flight, or with dieback, to check on "
        "the ground.",
    ),
)
KEYS: tuple[str, ...] = tuple(s.key for s in SWITCHES)


class SwitchError(ValueError):
    """An analysis name that does not exist."""


def checked(off: Iterable[str]) -> tuple[str, ...]:
    """The switched-off analyses in the order of ``SWITCHES``; raises SwitchError for a typo."""
    wanted = set(off)
    unknown = sorted(wanted - set(KEYS))
    if unknown:
        raise SwitchError(
            f"no analysis called {', '.join(unknown)}; the analyses are {', '.join(KEYS)}"
        )
    return tuple(k for k in KEYS if k in wanted)


def on(key: str, off: Iterable[str]) -> bool:
    return key not in set(off)


def trim_metrics(metrics: dict[str, Any], off: Iterable[str]) -> dict[str, Any]:
    """The metrics without those of the analyses switched off."""
    dropped = {m for s in SWITCHES if s.key in set(off) for m in s.metrics}
    return {k: v for k, v in metrics.items() if k not in dropped}


def describe(off: Iterable[str]) -> str:
    found = checked(off)
    if not found:
        return "all analyses on"
    titles = {s.key: s.title for s in SWITCHES}
    return "switched off: " + ", ".join(titles[k] for k in found)
