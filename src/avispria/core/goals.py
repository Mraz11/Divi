# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""From what you want to measure to how to fly: ground resolution, overlap and height, or an
honest "this cannot be done from a mapping flight".

Each goal has a rule for the coarsest ground resolution (GSD) that still shows it, and the overlap
that lets photogrammetry rebuild it:

* general mapping (the default): what will be measured is decided after the flight, when the
  maps are made, so the flight keeps every later analysis open: the finest any of them needs
  (2 cm, for crown symptoms and small plants) and the overlap tree heights need (85 / 75 %);
  only leaf lesions stay out of reach

* crowns of a given width: the surface model is made at 4x the photos' GSD (Standard preset),
  and a crown needs about 6 surface cells across to be outlined: GSD <= width / 24
* tree heights: GSD <= 5 cm and high overlap (85 / 75 %), because leaves move and repeat
  (Dandois et al. 2015 found canopy heights improve with overlap); open ground in the area
* canopy or crop cover: a patch of the given size needs about 4 pixels across: GSD <= size / 4
* counting plants or seedlings of a given width: about 5 pixels across: GSD <= width / 5
* visible crown symptoms (discoloured or dying patches of a given size): about 5 pixels across,
  and at most 3 cm; the sun 35 degrees up or more, a fixed white balance
* leaf lesions or leaf-level damage: about 5 pixels across a lesion; lesions are millimetres,
  so this needs about 0.5 mm per pixel (Van De Vijver et al. 2022), which no mapping flight
  reaches: the drone would have to fly closer than it safely can over a canopy
* buildings and town cover: GSD <= 5 cm, 80 / 70 % overlap, and a tilted pass for walls

The height then follows from the camera. A goal is not reachable when the height comes out lower
than ``MIN_CLEARANCE_M`` above the surface (rotor wash moves the leaves, and branches are close),
and the height is capped at 120 m (the usual legal limit), where a finer GSD is simply better.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from avispria.core.camera import CameraProfile, altitude_for_gsd, gsd_m

MIN_CLEARANCE_M = 15.0
MAX_AGL_M = 120.0
DEM_FACTOR = 4.0
CELLS_PER_CROWN = 6


@dataclass(frozen=True)
class Goal:
    key: str
    title: str
    size_label: str  # what the size means; "" when the goal has no size
    default_size_m: float
    front: float
    side: float
    cap_gsd_m: float  # never coarser than this, whatever the size
    per_size: float  # GSD = size / per_size (0: the size does not set it)
    notes: tuple[str, ...] = ()


GOALS: dict[str, Goal] = {
    g.key: g
    for g in (
        Goal("general", "General mapping (decide what to measure later)", "", 0.0,
             0.85, 0.75, 0.02, 0.0,
             ("keeps crowns, heights, cover, crown symptoms and buildings open; choose what to "
              "measure when the maps are made",
              "include some open ground, and fly with the sun 35 degrees up or more")),
        Goal("crowns", "Tree crowns (outlines, counts)", "Smallest crown width (m)", 3.0,
             0.85, 0.75, 0.10, DEM_FACTOR * CELLS_PER_CROWN,
             ("dense canopy: turn on the DeepForest crown pass when making the maps",)),
        Goal("heights", "Tree heights, biomass and carbon", "", 0.0, 0.85, 0.75, 0.05, 0.0,
             ("include some open ground in the area: heights are measured from it",
              "measure 5 or more trees on the ground to correct the heights",
              "a tilted loop around the area helps against doming")),
        Goal("cover", "Canopy or crop cover", "Smallest patch to see (m)", 0.5,
             0.80, 0.70, 0.05, 4.0, ()),
        Goal("plants", "Counting plants or seedlings", "Plant width (m)", 0.10,
             0.80, 0.70, 0.05, 5.0, ("fly early in the season, before plants touch",)),
        Goal("symptoms", "Visible crown symptoms (yellowing, browning, dieback)",
             "Smallest affected patch (m)", 0.5, 0.80, 0.70, 0.03, 5.0,
             ("fly with the sun 35 degrees up or more; fix the camera's white balance",
              "visible symptoms only: infection before symptoms needs other sensors")),
        Goal("lesions", "Leaf lesions or leaf-level damage", "Lesion size (m)", 0.005,
             0.80, 0.70, 0.0005, 5.0,
             ("use close-up photos instead: from a hovering drone 1 to 3 m away, or by hand",)),
        Goal("buildings", "Buildings, roads and town cover", "", 0.0, 0.80, 0.70, 0.05, 0.0,
             ("add a tilted pass (3D of an area) to see walls",)),
    )
}  # fmt: skip


@dataclass(frozen=True)
class Advice:
    goal: str
    gsd_m: float  # the coarsest that works (capped by the camera and 120 m)
    agl_m: float  # height above the surface for that GSD
    front: float
    side: float
    reachable: bool
    notes: list[str] = field(default_factory=list)

    @property
    def gsd_cm(self) -> float:
        return self.gsd_m * 100


def advise(key: str, size_m: float | None, cam: CameraProfile) -> Advice:
    """How to fly for goal ``key`` (one of GOALS) with this camera."""
    if key not in GOALS:
        raise ValueError(f"unknown goal {key!r}; choose {', '.join(GOALS)}")
    goal = GOALS[key]
    size = goal.default_size_m if size_m is None else size_m
    if goal.per_size and not size > 0:
        raise ValueError("the size must be more than zero")
    need = goal.cap_gsd_m if not goal.per_size else min(goal.cap_gsd_m, size / goal.per_size)
    agl = altitude_for_gsd(cam, need)
    notes = list(goal.notes)
    if agl > MAX_AGL_M:
        agl = MAX_AGL_M
        need = gsd_m(cam, agl)
        notes.insert(0, f"even at {MAX_AGL_M:.0f} m the detail is more than enough")
    reachable = agl >= MIN_CLEARANCE_M
    if not reachable:
        notes.insert(
            0,
            f"not reachable from a mapping flight: it needs {need * 1000:.1f} mm per pixel, "
            f"which means flying {agl:.1f} m above the surface (less than the "
            f"{MIN_CLEARANCE_M:.0f} m a drone needs above a canopy)",
        )
    return Advice(key, need, round(agl, 1), goal.front, goal.side, reachable, notes)


def describe(advice: Advice) -> str:
    """One paragraph for the screen and the command line."""
    head = (
        [
            f"Fly at {advice.agl_m:.0f} m for {advice.gsd_cm:.1f} cm per pixel, with "
            f"{advice.front * 100:.0f}% overlap along the lines and {advice.side * 100:.0f}% "
            "between them."
        ]
        if advice.reachable
        else []
    )
    return " ".join([*head, *(n[0].upper() + n[1:] + "." for n in advice.notes)])
