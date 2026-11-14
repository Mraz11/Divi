# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fly: step 3. Nothing to do on the computer: what to check, and what to do after landing."""

from __future__ import annotations

from nicegui import ui

from avispria.app.ui.layout import frame
from avispria.app.ui.state import STATE

FIELD_PAGE = "https://mraz11.github.io/Divi/"
BEFORE = (
    "In DJI Fly, open each mission and compare what its map shows (waypoints, length, time) with "
    "the 'DJI Fly should show' column on the Plan screen, and its heights with the spot-check "
    "sheet (the .csv next to each mission file). If they differ, do not fly it.",
    "Charge a battery for each mission, or for two or three short ones: the plan gives the "
    "minutes.",
    "The phone page has checklists, calculators and a flight log. It works without a signal "
    "once it has been opened (address below).",
)
DIFFERENT = (
    "In DJI Fly open the mission's settings and read Global Speed. It should be the speed in the "
    "plan.",
    "To see what DJI Fly really holds, pull the mission back from the phone and inspect it. In a "
    "terminal: avispria phone slots (lists the missions), then avispria phone pull <ID> --out "
    "<a folder>, then avispria inspect <that file>.kmz. It prints the speeds, the route and the "
    "time, and says so if the speeds in the file disagree.",
    "If the numbers still differ, do not fly that mission, and send the output of inspect to the "
    "developers.",
)
AT_THE_SITE = (
    "Check the rules where you fly, the wind and the GPS lock before you take off.",
    "Keep the aircraft in sight. Your hand stays ready on the sticks: you can take over at any "
    "time.",
    "The first time, fly a small test area in open, flat terrain.",
)
CAMERA = (
    "Photo size: 12 MP (DJI Fly camera settings). In 48 MP mode the Lito X1 needs about 6.5 s "
    "per photo: photos then fall between waypoints, some are never taken, and the last waypoint "
    "keeps shooting while the drone hovers. Plan with the 48 MP mode if you want 48 MP.",
    "Exposure: switch from Auto to Pro (M). Shutter 1/1000 s (1/500 s in poor light), ISO Auto. "
    "In Auto, DJI Fly chose 1/20 to 1/80 s in the first test flight: at 5 m/s that smears every "
    "photo by 6 to 25 cm.",
    "Camera straight down (-90 degrees) for a flat map; focus on infinity (tap far ground).",
    "Fly in steady light: overcast or mid-morning. Low sun gives long shadows and slow shutters.",
    "A photo at every waypoint needs no timer setting. If you planned with timed shot, set that "
    "interval in DJI Fly first.",
)
INTERRUPTED = (
    "Stopped halfway (low battery, signal, you took over): land, change the battery, open the "
    "same mission in DJI Fly and start it again. If DJI Fly offers to continue from where it "
    "stopped, take it (not yet tried with the Lito X1); otherwise fly the whole mission again. "
    "Keep all photos in the one folder: the repeated part is found and left out.",
    "Flown twice, or the same ground photographed twice: nothing is lost. Check photos and Make "
    "maps find the repeated pass and keep only the sharper one, so processing does not take "
    "twice as long or mix two lights. Photos taken while hovering are left out too.",
    "A second flight of the same plan another day (for change over time) goes in its own folder "
    "and is processed on its own.",
)
AFTER = (
    "Copy the photos from the memory card to ONE folder on this computer (all missions of a "
    "flight together).",
    "Keep the folder as it is: do not rename or edit the photos.",
    "Then go on to the next step, which checks that the photos overlap enough.",
)


def _card(title: str, lines: tuple[str, ...], marker: str) -> None:
    with ui.card().classes("w-full gap-2").mark(marker):
        ui.label(title).classes("text-lg font-bold")
        for line in lines:
            with ui.row().classes("items-start gap-2 no-wrap"):
                ui.icon("check_circle_outline").classes("av-muted")
                ui.label(line).classes("text-sm")


async def fly_page() -> None:
    with frame("Fly"):
        count = len(STATE.last_plan_files)
        if count:
            plural = "missions" if count != 1 else "mission"
            ui.label(f"Your last plan has {count} {plural}.").classes("font-medium").mark(
                "fly-plan-count"
            )
        _card("Before you leave", BEFORE, "fly-before")
        ui.link(FIELD_PAGE, FIELD_PAGE, new_tab=True).classes("text-sm")
        _card("If DJI Fly shows different numbers", DIFFERENT, "fly-different")
        _card("Camera settings in DJI Fly (every flight)", CAMERA, "fly-camera")
        _card("At the site", AT_THE_SITE, "fly-site")
        _card("If a flight stops, or is flown twice", INTERRUPTED, "fly-interrupted")
        _card("After landing", AFTER, "fly-after")
