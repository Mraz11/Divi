# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional inputs of the tree inventory on the Make maps screen.

All of them make the tree numbers better; none is needed. Without them the inventory still runs:
the ground comes from this flight, doming is not checked, heights are not corrected, and the
biomass uses a typical wood density, with ranges that say how unsure that is.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.adapters import tree_detector
from avispria.adapters.area_file import SUFFIXES as AREA_SUFFIXES
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.ui.pages.plan_form_parts import number, select_fit
from avispria.app.ui.widgets import PathField
from avispria.core.biomass import BiomassInputs
from avispria.core.ground_sources import KIND_TEXT, OUTSIDE_KINDS

HELP = (
    "Optional, for forests and trees. Each one makes the heights, biomass and carbon better: "
    "a ground model from elsewhere (under a closed canopy the drone hardly sees the ground), an "
    "independent ground model to check that the 3D model is not bent (doming), and a few trees "
    "measured on the ground to correct the heights (a CSV with lat, lon and height_m columns; "
    "5 or more trees for a full correction)."
)
TIFF = (".tif", ".tiff")


class TreeSection:
    def __init__(self, opened: bool = False) -> None:
        with (
            ui.expansion(
                "Trees: heights, biomass and carbon (optional inputs)", icon="park", value=opened
            )
            .classes("w-full border")
            .mark("trees-inputs"),
            ui.column().classes("w-full gap-3 p-2"),
        ):
            ui.label(HELP).classes("text-sm av-muted")
            with ui.row().classes("w-full gap-2 items-start no-wrap"):
                with ui.column().classes("grow"):
                    self.ground = PathField(
                        "Ground model from elsewhere (GeoTIFF)",
                        directory=False,
                        suffixes=TIFF,
                        marker="trees-ground",
                    )
                self.kind = ui.select(
                    {k: KIND_TEXT[k] for k in OUTSIDE_KINDS}, value="lidar", label="It is"
                ).props("outlined dense")
                select_fit(self.kind.mark("trees-ground-kind"), "It is")
            self.reference = PathField(
                "Independent ground model for the doming check (GeoTIFF)",
                directory=False,
                suffixes=TIFF,
                marker="trees-reference",
            )
            self.field = PathField(
                "Trees measured on the ground (CSV)",
                directory=False,
                suffixes=(".csv",),
                marker="trees-field",
            )
            with ui.row().classes("gap-2"):
                self.density = number(
                    "Wood density (g/cm3)", 0.6, "trees-density", min=0.1, max=1.5, step=0.05
                )
                self.density_sd = number(
                    "Its uncertainty (g/cm3)", 0.1, "trees-density-sd", min=0, max=0.5, step=0.01
                )
                self.carbon = number(
                    "Carbon share of the wood", 0.47, "trees-carbon", min=0.3, max=0.6, step=0.01
                )
            self.conifer = ui.switch("Mostly conifers (pines, firs)").mark("trees-conifer")
            ready = tree_detector.available()
            self.deepforest = ui.switch(
                "Correct the crowns with DeepForest (a pretrained tree detector)", value=ready
            ).mark("trees-deepforest")
            ui.label(
                "Helps in dense or mixed canopy, where the height model merges or splits crowns. "
                + (
                    "Installed."
                    if ready
                    else f"Not installed (about 1 to 2 GB): run {tree_detector.INSTALL} in the "
                    "Dīvi folder, then start Dīvi again."
                )
            ).classes("text-sm av-muted")
            ui.label(
                "Wood density: the mean of the main species (Global Wood Density Database); "
                "0.6 is a typical broadleaf value. Carbon share 0.47 is the IPCC default."
            ).classes("text-sm av-muted")

    def inputs(self) -> TreeInputs:
        def path(field: PathField) -> Path | None:
            text = (field.value or "").strip()
            return Path(text).expanduser() if text else None

        return TreeInputs(
            ground_file=path(self.ground),
            ground_kind=str(self.kind.value or "lidar"),
            reference_file=path(self.reference),
            field_heights=path(self.field),
            deepforest=bool(self.deepforest.value),
            biomass=BiomassInputs(
                wood_density=float(self.density.value or 0.6),
                wood_density_sd=float(self.density_sd.value or 0.0),
                carbon_fraction=float(self.carbon.value or 0.47),
                conifer=bool(self.conifer.value),
            ),
        )


CLIP_HELP = (
    "Optional. Right after the photos are stitched, the orthophoto and the surface and ground "
    "models are cut to this area, so every number is about your study area only. KML or KMZ, a "
    "shapefile (.shp, with its .shx, .dbf and .prj beside it), a .zip with one, or GeoJSON. The "
    "uncut maps are kept beside them (*.full.tif)."
)


class ClipSection:
    """Extract by mask: the area to cut the stitched maps to, and a buffer."""

    def __init__(self, opened: bool = False) -> None:
        with (
            ui.expansion("Cut the maps to your area (optional)", icon="crop_square", value=opened)
            .classes("w-full border")
            .mark("clip-inputs"),
            ui.column().classes("w-full gap-3 p-2"),
        ):
            ui.label(CLIP_HELP).classes("text-sm av-muted")
            self.file = PathField(
                "Area to cut by", directory=False, suffixes=AREA_SUFFIXES, marker="clip"
            )
            self.buffer = number(
                "Widen it by (m)", 0.0, "clip-buffer", "w-48", min=0, max=5000, step=1
            )

    def values(self) -> tuple[str, float]:
        return (self.file.value or "").strip(), float(self.buffer.value or 0.0)
