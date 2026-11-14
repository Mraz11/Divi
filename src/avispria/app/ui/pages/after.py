# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Steps 5 and 6: cut maps that are already made, and measure them again.

'Make maps' does both by itself when asked. These screens do each on its own, on any maps folder:
to cut by another area, to add trees measured on the ground, or to measure maps made earlier,
without stitching the photos again.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from nicegui import ui

from avispria.app.ui.after_job import (
    AfterError,
    maps_folder,
    read_provenance,
    run_cut,
    run_measure,
    undo_cut,
)
from avispria.app.ui.jobs import run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.pages.analysis_section import show_analysis
from avispria.app.ui.pages.analysis_switches import SwitchSection
from avispria.app.ui.pages.canopy_section import show_canopy
from avispria.app.ui.pages.plan_form_parts import select_fit
from avispria.app.ui.pages.process_trees import ClipSection, TreeSection
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField
from avispria.core.profiles import PROFILES

FOLDER_HINT = "The folder that 'Make maps' saved to. It has a 'results' folder inside."
WHAT = "What did you map? (decides what is measured)"


def _problem(box: ui.column, text: str) -> None:
    box.clear()
    with box:
        ui.label(text).classes("av-problem-text font-medium").mark("after-problem")


def _busy(box: ui.column, text: str) -> None:
    box.clear()
    with box, ui.row().classes("items-center gap-2"):
        ui.spinner(size="md")
        ui.label(text)


async def cut_page() -> None:
    with frame("Cut the maps"):
        ui.label(
            "Cut the orthophoto and the surface and ground models to your study area, so every "
            "number measured afterwards is about that area only. The uncut maps are kept beside "
            "them (*.full.tif), and you can undo the cut."
        ).classes("text-base")
        folder = PathField(
            "Maps folder", value=STATE.maps_folder, marker="cut-folder", hint=FOLDER_HINT
        )
        part = ClipSection(opened=True)
        with ui.row().classes("gap-2 items-center"):
            cut_button = ui.button("Cut the maps", icon="crop_square").props("no-caps size=lg")
            cut_button.mark("cut-button")
            undo_button = ui.button("Undo the cut", icon="undo").props("no-caps outline")
            undo_button.mark("uncut-button")
        box = ui.column().classes("w-full gap-2").mark("cut-result")

    async def cut() -> None:
        file, buffer_m = part.values()
        _busy(box, "Cutting the maps...")
        cut_button.disable()
        outcome = await run_job(run_cut, folder.value, file, buffer_m)
        cut_button.enable()
        if not outcome.ok or outcome.value is None:
            _problem(box, outcome.error or "The maps were not cut.")
            return
        done = outcome.value
        box.clear()
        with box:
            size = "" if done.area_m2 is None else f" ({done.area_m2 / 10_000:.2f} ha)"
            ui.label(f"Cut{size}: {', '.join(p.name for p in done.cut)}.").classes("font-medium")
            for note in done.notes:
                ui.label(f"- {note}").classes("text-sm av-muted")
            ui.label(
                "Numbers measured before the cut are about the whole map. Measure again "
                "(step 6) to get them for this area."
            ).classes("text-sm")

    async def undo() -> None:
        outcome = await run_job(undo_cut, folder.value)
        if not outcome.ok or outcome.value is None:
            _problem(box, outcome.error or "Nothing was undone.")
            return
        box.clear()
        with box:
            names = ", ".join(p.name for p in outcome.value)
            ui.label(f"The uncut maps are back: {names}.").classes("font-medium")

    cut_button.on_click(cut)
    undo_button.on_click(undo)


def _show_measured(box: ui.column, folder: Path, canopy: object) -> None:
    box.clear()
    with box:
        show_analysis(folder)
        show_canopy(canopy if isinstance(canopy, dict) else {}, folder)
        ui.label(f"Saved in {folder / 'results' / 'analysis'}").classes(
            "text-sm av-muted break-all"
        )


async def measure_page() -> None:
    with frame("Measure"):
        ui.label(
            "Measure canopy height, trees, cover and biomass from maps that are already made. "
            "'Make maps' measures once by itself; measure again here after cutting the maps, or "
            "to add a better ground model or trees measured on the ground. The photos are not "
            "stitched again."
        ).classes("text-base")
        folder = PathField(
            "Maps folder", value=STATE.maps_folder, marker="measure-folder", hint=FOLDER_HINT
        )
        mapped = (
            ui.select({name: p.title for name, p in PROFILES.items()}, value="forest", label=WHAT)
            .classes("w-80")
            .mark("measure-profile")
        )
        select_fit(mapped, WHAT)
        switches = SwitchSection(opened=True)
        trees = TreeSection()
        button = ui.button("Measure", icon="fact_check").props("no-caps size=lg")
        button.mark("measure-button")
        box = ui.column().classes("w-full gap-2").mark("measure-result")

    async def measure() -> None:
        _busy(box, "Measuring... a large map takes a few minutes.")
        button.disable()
        inputs = replace(trees.inputs(), off=switches.off())
        outcome = await run_job(run_measure, folder.value, str(mapped.value), inputs)
        button.enable()
        if not outcome.ok or outcome.value is None:
            _problem(box, outcome.error or "Nothing was measured.")
            return
        _show_measured(box, maps_folder(folder.value), outcome.value)

    button.on_click(measure)
    try:  # measurements made earlier (by 'Make maps' or here) are shown straight away
        found = maps_folder(folder.value)
    except AfterError:
        return
    _show_measured(box, found, read_provenance(found))
