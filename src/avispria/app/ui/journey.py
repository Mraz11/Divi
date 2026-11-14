# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The way through a project: the screens of the engines, in order, defined once.

The engines come from ``core/pipeline.py``. Each has one screen, except Mission, which has two
(send the missions, then fly). The top bar, the Start page and every screen use this list, so a
person always knows where they are, can go back, and sees what comes next.
"""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from avispria.app.project import ProjectError, default_root
from avispria.app.ui import projects
from avispria.app.ui.progress import new_project
from avispria.core.pipeline import AFTER_FLIGHT, ENGINES, TOTAL, engine


@dataclass(frozen=True)
class Step:
    number: int  # the number of its engine in the pipeline
    title: str  # the screen's title
    path: str
    icon: str
    what: str  # what you do here, in one sentence
    engine: str  # key of the engine it belongs to


STEPS = (
    Step(
        1,
        "Plan a flight",
        "/plan",
        "edit_location_alt",
        "Choose what you want to capture, mark the place, and get missions for DJI Fly.",
        "plan",
    ),
    Step(
        2,
        "Send to DJI Fly",
        "/phone",
        "send",
        "Put the missions into DJI Fly on your phone, over a USB cable or Wi-Fi.",
        "mission",
    ),
    Step(
        2,
        "Fly",
        "/fly",
        "flight_takeoff",
        "Check the aircraft and the missions in DJI Fly, then fly. Nothing to do on the computer.",
        "mission",
    ),
    Step(
        3,
        "Check my photos",
        "/check",
        "photo_library",
        "Copy the photos to this computer and see whether they overlap enough.",
        "photos",
    ),
    Step(
        4,
        "Make maps",
        "/process",
        "map",
        "Turn the photos into a map or a 3D model with WebODM, on this computer.",
        "reconstruct",
    ),
    Step(
        5,
        "Cut the maps",
        "/map",
        "crop_square",
        "Cut the stitched maps to your study area. Optional: skip it to keep the whole map.",
        "map",
    ),
    Step(
        6,
        "Measure",
        "/analyse",
        "fact_check",
        "Measure canopy height, trees, cover and biomass from the maps, again or with field data.",
        "analyse",
    ),
    Step(
        7,
        "Export",
        "/export",
        "output",
        "Save the maps and measurements as files for QGIS and other programs: one file per band.",
        "export",
    ),
    Step(
        7,
        "Map images",
        "/figure",
        "image",
        "Make map images for papers and posters: size, resolution, legend, north arrow, scale.",
        "export",
    ),
    Step(
        8,
        "Report",
        "/report",
        "description",
        "Make one report of the project: results with ranges, maps, methods, and how to cite.",
        "report",
    ),
)
START = ("Start", "/")


def step_for(title: str) -> Step | None:
    return next((s for s in STEPS if s.title == title), None)


def nav_label(step: Step) -> str:
    return f"{step.number}. {step.title}"


def screens(maps_only: bool = False) -> tuple[Step, ...]:
    """The screens in order; Dīvi Maps has only those after the flight."""
    return tuple(s for s in STEPS if not maps_only or s.engine in AFTER_FLIGHT)


def first_screen(key: str) -> Step:
    return next(s for s in STEPS if s.engine == key)


def nav_items(maps_only: bool = False) -> tuple[tuple[str, str, str], ...]:
    """(label, path, engine key) of every item in the top bar: Start, then the engines."""
    items = [(*START, "")] if not maps_only else []
    for spec in ENGINES:
        if not maps_only or spec.key in AFTER_FLIGHT:
            items.append((f"{spec.number} {spec.name}", first_screen(spec.key).path, spec.key))
    return tuple(items)


def neighbours(step: Step, maps_only: bool = False) -> tuple[Step | None, Step | None]:
    """The screen before and the screen after this one."""
    order = screens(maps_only)
    at = order.index(step)
    return (order[at - 1] if at > 0 else None, order[at + 1] if at + 1 < len(order) else None)


def _go(step: Step, forward: bool, marker: str, solid: bool = False) -> None:
    """A button to the screen before or after."""
    props = "no-caps" + ("" if solid else " outline")
    if forward:
        button = ui.button(f"Next: {nav_label(step)}").props(f"{props} icon-right=arrow_forward")
    else:
        button = ui.button(f"Back: {nav_label(step)}", icon="arrow_back").props(props)
    button.on_click(lambda: ui.navigate.to(step.path))
    button.mark(marker)


def journey_bar(step: Step, maps_only: bool = False) -> None:
    """'Step 2 of 8': which engine this is, what you do here, where it stands, back and next."""
    spec = engine(step.engine)
    state = projects.state_of(step.engine)
    with ui.card().classes("w-full av-note-info").mark("journey-bar"):
        with ui.row().classes("w-full items-center gap-2"):
            ui.badge(f"Step {step.number} of {TOTAL}").props("color=primary").mark("step-badge")
            ui.label(spec.name).classes("av-label")
            ui.space()
            ui.chip(
                state.label,
                icon="check_circle" if state.done else "radio_button_unchecked",
                color="positive" if state.done else "grey-5",
            ).props("dense").mark("step-status")
        ui.label(step.what).classes("text-sm font-medium")
        ui.label(state.detail).classes("text-sm av-muted").mark("step-detail")
        before, after = neighbours(step, maps_only)
        with ui.row().classes("w-full gap-2 items-center").mark("journey-moves"):
            if before is not None:
                _go(before, False, "back-button")
            ui.space()
            if after is not None:
                _go(after, True, "forward-button")


def next_step_card(step: Step, maps_only: bool = False) -> None:
    """At the bottom of a screen: back, and where to go once this one is done."""
    before, after = neighbours(step, maps_only)
    with ui.card().classes("w-full av-note-info").mark("next-step"):
        if after is not None:
            ui.label("When you are done here").classes("font-bold")
            ui.label(after.what).classes("text-sm")
        else:
            ui.label("That is the whole journey").classes("font-bold")
            ui.label(
                "Open the maps folder to see your maps, measurements and the report. To "
                "fly somewhere else, start a new project: nothing is deleted."
            ).classes("text-sm")
        with ui.row().classes("w-full gap-2 items-center"):
            if before is not None:
                _go(before, False, "back-step-button")
            ui.space()
            if after is not None:
                _go(after, True, "next-step-button", solid=True)
            elif not maps_only:
                ui.button("Start a new project", icon="replay", on_click=ask_new_project).props(
                    "no-caps"
                ).mark("next-step-button")


def ask_new_project() -> None:
    with ui.dialog() as dialog, ui.card().classes("gap-3").mark("new-project-dialog"):
        ui.label("Start a new project?").classes("text-lg font-bold")
        ui.label(
            "The steps start again. Nothing is deleted: this project's missions, photos and "
            "maps stay where they are. Your sample mission and phone set-up are kept."
        )
        name = (
            ui.input("Name of the new project (optional)", placeholder="Sal forest, block A")
            .classes("w-full")
            .mark("new-project-name")
        )
        ui.label(
            f"With a name, the project gets its own folder in {default_root()} and "
            "stays in the list on the Start page. Without one, only the steps start again."
        ).classes("text-sm av-muted")
        with ui.row().classes("justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")

            def confirm() -> None:
                wanted = (name.value or "").strip()
                try:
                    if wanted:
                        projects.start_project(wanted)
                    else:
                        new_project()
                except ProjectError as exc:
                    ui.notify(str(exc), type="negative")
                    return
                dialog.close()
                ui.navigate.to("/")

            ui.button("Start a new project", on_click=confirm).props("no-caps").mark(
                "new-project-confirm"
            )
    dialog.open()
