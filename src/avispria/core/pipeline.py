# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one pipeline: eight engines, in the order a project goes, defined once.

Every part of Dīvi is one of these engines. The screens, the command line and the report
all read this list, so the order, the names and what each engine needs are never written twice.

    Plan -> Mission -> Photo check -> Reconstruct -> Map -> Analyse -> Export -> Report

An engine takes what earlier engines made (``needs``) and makes its own products. Its state in a
project is worked out from what is on disk (``app/engines.py``), never from memory alone, so a
project can be closed, moved to another computer and continued.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["done", "partial", "ready", "waiting"]
STATUS_TEXT: dict[Status, str] = {
    "done": "Done",
    "partial": "Started, not finished",
    "ready": "Ready to do",
    "waiting": "Needs an earlier step",
}


@dataclass(frozen=True)
class EngineSpec:
    key: str
    number: int
    name: str  # the engine's short name, as in the diagram above
    task: str  # what it does, in one sentence
    makes: str  # its products
    needs: tuple[str, ...] = ()  # keys of the engines whose products it uses
    optional: bool = False  # a project is complete without it


ENGINES: tuple[EngineSpec, ...] = (
    EngineSpec(
        "plan",
        1,
        "Plan",
        "Works out the flight lines, height and speed for what you want to measure.",
        "missions for DJI Fly, with predicted detail and overlap",
    ),
    EngineSpec(
        "mission",
        2,
        "Mission",
        "Puts the missions into DJI Fly on the phone; then you fly them.",
        "missions on the phone, and the photos of the flight",
        ("plan",),
    ),
    EngineSpec(
        "photos",
        3,
        "Photo check",
        "Reads the photos' metadata and says whether they overlap enough to make a map.",
        "a verdict, a coverage map and warnings",
    ),
    EngineSpec(
        "reconstruct",
        4,
        "Reconstruct",
        "Stitches the photos into an orthophoto, a surface model and a point cloud (WebODM).",
        "orthophoto, surface and ground models, point cloud, a record of how they were made",
        ("photos",),
    ),
    EngineSpec(
        "map",
        5,
        "Map",
        "Cuts the stitched maps to your study area, so every number is about that area only.",
        "the maps cut to your area (the uncut ones are kept)",
        ("reconstruct",),
        optional=True,
    ),
    EngineSpec(
        "analyse",
        6,
        "Analyse",
        "Measures canopy height, trees, cover and biomass, each with its uncertainty.",
        "canopy height model, tree list, land cover, biomass with ranges, quality grades",
        ("reconstruct",),
    ),
    EngineSpec(
        "export",
        7,
        "Export",
        "Writes the maps and measurements as files for QGIS and other programs, and map images.",
        "one GeoTIFF per band with QGIS styles, a GeoPackage of editable layers, map images",
        ("reconstruct",),
    ),
    EngineSpec(
        "report",
        8,
        "Report",
        "Writes one report: results with ranges, maps, methods, checks, provenance, citation.",
        "the project report (one HTML file; print it to PDF)",
        ("reconstruct",),
    ),
)
TOTAL = len(ENGINES)
KEYS: tuple[str, ...] = tuple(e.key for e in ENGINES)
AFTER_FLIGHT: tuple[str, ...] = ("reconstruct", "map", "analyse", "export", "report")  # Dīvi Maps


def engine(key: str) -> EngineSpec:
    for spec in ENGINES:
        if spec.key == key:
            return spec
    raise KeyError(f"no engine called {key!r}; the engines are {', '.join(KEYS)}")


def blocked_by(key: str, done: frozenset[str] | set[str]) -> tuple[str, ...]:
    """The engines that must finish before this one can run."""
    return tuple(k for k in engine(key).needs if k not in done)


def status(key: str, *, finished: bool, started: bool, done: frozenset[str] | set[str]) -> Status:
    """An engine's state from what is on disk and which engines are done."""
    if finished:
        return "done"
    if started:
        return "partial"
    return "waiting" if blocked_by(key, done) else "ready"


def complete(done: frozenset[str] | set[str]) -> bool:
    """Is the project finished? Optional engines do not count."""
    return all(e.key in done for e in ENGINES if not e.optional)


def diagram() -> str:
    return " -> ".join(e.name for e in ENGINES)
