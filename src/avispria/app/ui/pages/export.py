# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Step 7: the maps and measurements as files for QGIS and other programs."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.export_workflow import EXPORT_DIR, ExportOptions
from avispria.app.ui.after_job import run_export_job
from avispria.app.ui.files import open_in_file_manager
from avispria.app.ui.jobs import run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField

FOLDER_HINT = "The folder that 'Make maps' saved to. It has a 'results' folder inside."
PARTS = (
    ("bands", "Red, green and blue as separate files", "One band per GeoTIFF, 0-255."),
    ("colour", "The full-colour orthophoto", "Red, green, blue and alpha in one GeoTIFF."),
    (
        "surfaces",
        "Surface, ground and canopy height models",
        "Heights in metres, and the uncertainty of the ground under each cell.",
    ),
    (
        "analysis",
        "Land cover and colour index bands",
        "Whatever was measured: land cover with its colour table, its confidence, one GeoTIFF per "
        "index.",
    ),
    (
        "vectors",
        "Editable layers (GeoPackage)",
        "Tree tops with heights and biomass, crowns, buildings and roads, in one file.",
    ),
)
ABOUT = (
    "Every file opens in QGIS (drag it in) already styled, and in any GIS or image program: "
    "Cloud-Optimised GeoTIFFs in the map's own coordinate system, a GeoPackage you can edit and "
    "save in place, a README and a manifest saying what each file is and its unit. The export "
    f"goes to the '{EXPORT_DIR}' folder inside the maps folder and is rebuilt each time."
)


async def export_page() -> None:
    with frame("Export"):
        ui.label(ABOUT).classes("text-base")
        folder = PathField(
            "Maps folder", value=STATE.maps_folder, marker="export-folder", hint=FOLDER_HINT
        )
        switches: dict[str, ui.switch] = {}
        with ui.card().classes("w-full gap-2").mark("export-parts"):
            ui.label("What to export").classes("font-bold")
            for key, title, what in PARTS:
                with ui.row().classes("w-full items-start gap-2 no-wrap"):
                    switches[key] = ui.switch(value=True).mark(f"export-{key}")
                    with ui.column().classes("gap-0"):
                        ui.label(title).classes("font-medium")
                        ui.label(what).classes("text-sm av-muted")
            with ui.row().classes("w-full items-start gap-2 no-wrap"):
                ui.switch(value=False).props("disable").mark("export-xylo")
                with ui.column().classes("gap-0"):
                    ui.label("Prepare for Xylo Forest").classes("font-medium")
                    ui.label(
                        "Coming: the files Xylo Forest needs will be added when its format is "
                        "settled. Until then, the files above open in it like in any GIS."
                    ).classes("text-sm av-muted")
        button = ui.button("Export", icon="output").props("no-caps size=lg").mark("export-button")
        box = ui.column().classes("w-full gap-2").mark("export-result")

    async def export() -> None:
        options = ExportOptions(**{key: bool(s.value) for key, s in switches.items()})
        box.clear()
        with box, ui.row().classes("items-center gap-2"):
            ui.spinner(size="md")
            ui.label("Exporting... a large orthophoto takes a few minutes.")
        button.disable()
        outcome = await run_job(run_export_job, folder.value, options)
        button.enable()
        box.clear()
        with box:
            if not outcome.ok or outcome.value is None:
                ui.label(outcome.error or "Nothing was exported.").classes(
                    "av-problem-text font-medium"
                ).mark("export-problem")
                return
            done = outcome.value
            ui.label(f"{len(done.files)} files in {done.folder}").classes("font-medium break-all")
            for item in done.files:
                ui.label(f"{item['file']}: {item['what']}").classes("text-sm")
            for text in done.skipped:
                ui.label(f"Not exported: {text}").classes("text-sm av-muted")
            ui.button(
                "Open the folder",
                icon="folder_open",
                color="secondary",
                on_click=lambda: open_in_file_manager(Path(done.folder)),
            ).props("no-caps").mark("export-open")

    button.on_click(export)
