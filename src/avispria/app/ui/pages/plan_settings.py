# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The settings cards of the Plan a flight form: what you want, the ground, saving, advanced."""

from __future__ import annotations

import math
from typing import Any

from nicegui import ui

from avispria.app.ui.pages.plan_form_parts import (
    card,
    fit,
    number,
    select_fit,
    show_when,
    text,
)
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField
from avispria.core.goals import GOALS, advise
from avispria.core.goals import describe as describe_advice

PHOTO_MODE_HELP = (
    "A photo at every photo point: Dīvi puts a waypoint wherever a photo is taken, so you see "
    "every photo position in DJI Fly and the camera needs no setting. It makes more missions, "
    "because DJI Fly takes about 99 waypoints in one. Timed shot: only the ends of the lines are "
    "waypoints and the camera shoots on a timer that you must set in DJI Fly."
)

AREA_KINDS = ("flat", "area_3d")
TILT_HELP = (
    "How far the camera leans from straight down. About 30 degrees sees the sides of trees and "
    "buildings as well as the ground; more shows more of the sides but gives coarser detail at the "
    "top of each picture. The lines are flown in two directions."
)


SPEED_HELP = (
    "Dīvi flies as fast as the photos allow: the slowest of motion blur, the camera's time "
    "between photos, the wind and the drone's top speed sets the speed (the plan says which). "
    "Lower the fastest speed to fly slower. The time between photos is the camera's; if your "
    "drone takes photos faster than this (time it on a test flight), lower it and the plan can "
    "fly faster."
)


class SettingsCards:
    """The cards below the drone card. ``PlanFormUi`` builds them in order."""

    profiles: dict[str, Any]

    def _goal_row(self) -> None:
        """What do you want to measure? -> resolution, overlap and height, or a warning."""
        with ui.row().classes("gap-2 items-center"):
            self.goal = ui.select(
                {k: g.title for k, g in GOALS.items()},
                value="general",
                label="What will you measure?",
            ).props("outlined dense")
            select_fit(self.goal.mark("goal-select"), "What will you measure?")
            self.goal_size = number(
                "Size (m)", 3.0, "goal-size", "w-44", min=0.0005, max=100, step=0.1
            )
            ui.button("Suggest settings", icon="auto_fix_high", on_click=self.suggest).props(
                "outline"
            ).mark("goal-suggest")
        self.goal_note = ui.label().classes("text-sm").mark("goal-note")

        def size_for(key: str) -> None:
            goal = GOALS[key]
            self.goal_size.set_visibility(bool(goal.size_label))
            self.goal_size.props(f'label="{goal.size_label or "Size (m)"}"')
            fit(self.goal_size, goal.size_label or "Size (m)", ["0.005"])
            self.goal_size.set_value(goal.default_size_m or None)
            self.goal_note.set_text("")

        self.goal.on_value_change(lambda e: size_for(e.value))
        size_for("general")

    def suggest(self) -> None:
        profile = self.profiles[self.aircraft.value]
        cam = profile.modes[self.camera.value]
        try:
            advice = advise(self.goal.value, self.goal_size.value, cam)
        except ValueError as exc:
            self.goal_note.set_text(str(exc))
            return
        self.goal_note.set_text(describe_advice(advice))
        self.goal_note.classes(
            add="av-good-text" if advice.reachable else "av-problem-text",
            remove="av-problem-text" if advice.reachable else "av-good-text",
        )
        if advice.reachable:
            self.target_kind.set_value("resolution")
            self.target.set_value(math.floor(advice.gsd_cm * 10) / 10 or 0.1)
            self.front.set_value(round(advice.front * 100))
            self.side.set_value(round(advice.side * 100))

    def _wants_card(self) -> None:
        with card("4. Settings", radio=self.scan_type, kinds=AREA_KINDS):
            self._goal_row()
            self.target_kind = (
                ui.radio(
                    {"resolution": "A ground resolution", "height": "A flying height"},
                    value="resolution",
                )
                .props("inline")
                .mark("target-kind")
            )
            with ui.row().classes("gap-2 items-center"):
                self.target = number("Value", 2.0, "target-input", min=0.1, max=300)
                unit = ui.label().classes("text-sm av-muted")
            unit.bind_text_from(
                self.target_kind,
                "value",
                backward=lambda v: (
                    "cm per pixel (smaller = more detail)"
                    if v == "resolution"
                    else "metres above the surface"
                ),
            )
            with ui.row().classes("gap-2"):
                self.front = number(
                    "Overlap along the line (%)", 80.0, "front-input", "w-60", min=10, max=95
                )
                self.side = number(
                    "Overlap between lines (%)", 70.0, "side-input", "w-60", min=10, max=95
                )
            with show_when(self.scan_type, "area_3d", gap="gap-1"):
                self.tilt = number(
                    "Camera tilt (degrees from straight down)",
                    30.0,
                    "tilt-input",
                    "w-96",
                    min=10,
                    max=50,
                )
                ui.label(TILT_HELP).classes("text-sm av-muted")
            self.photo_mode = (
                ui.select(
                    {
                        "waypoint": "A photo at every photo point (recommended)",
                        "interval": "Timed shot (fewer waypoints)",
                    },
                    value="waypoint",
                    label="How photos are taken",
                )
                .props("outlined dense")
                .classes("w-96")
                .mark("photo-mode-select")
            )
            select_fit(self.photo_mode, "How photos are taken")
            ui.label(PHOTO_MODE_HELP).classes("text-sm av-muted")
            self._ground_section()

    def _ground_section(self) -> None:
        ui.separator()
        ui.label("The ground").classes("text-base font-bold")
        with ui.column().classes("w-full gap-2"):
            self.terrain = (
                ui.radio(
                    {"flat": "It is flat", "model": "It has hills (I have an elevation model)"},
                    value="flat",
                )
                .props("inline")
                .mark("terrain")
            )
            with show_when(self.terrain, "model", gap="gap-1"):
                self.dem = PathField(
                    "Elevation model (GeoTIFF)",
                    directory=False,
                    suffixes=(".tif", ".tiff"),
                    marker="dem",
                    hint="With hills, the route follows the terrain so the photos keep "
                    "their resolution.",
                )
            self.surface = number(
                "Height of trees or buildings above the ground (m)",
                0.0,
                "surface-input",
                "w-96",
                min=0,
                max=150,
            )
            ui.label(
                "In a forest enter the typical canopy height, so the canopy (not the ground) "
                "gets the height you asked for. Leave 0 for open ground."
            ).classes("text-xs av-muted")

    def _speed_fields(self) -> None:
        profile = self.profiles[self.first]
        mode = profile.modes.get("12mp") or next(iter(profile.modes.values()))
        with ui.row().classes("gap-2"):
            self.speed_limit = number(
                "Fastest flying speed (m/s)",
                profile.max_speed_ms,
                "speed-limit-input",
                "w-64",
                min=1,
                max=profile.max_speed_ms,
                step=0.5,
            )
            self.interval = number(
                "Shortest time between photos (s)",
                mode.min_interval_s,
                "interval-input",
                "w-72",
                min=0.3,
                max=30,
                step=0.1,
            )
        speed_help = ui.label(SPEED_HELP).classes("text-sm av-muted")
        for widget in (self.speed_limit, self.interval, speed_help):
            widget.bind_visibility_from(self.scan_type, "value", backward=lambda v: v in AREA_KINDS)

    def _save_card(self) -> None:
        with card("5. Where to save"):
            self.out = PathField("Output folder", value=STATE.last_output, marker="out")
            self.name = text("Name for the missions", "name-input", "survey", "w-64")

    def _advanced(self) -> None:
        with (
            ui.expansion("Advanced settings", icon="tune").classes("w-full border"),
            ui.column().classes("gap-2 p-2"),
        ):
            self.shutter = text("Shutter time you expect", "shutter-input", "1/1000", "w-60")
            with ui.row().classes("gap-2"):
                self.wind = number("Wind (m/s)", 0.0, "wind-input", min=0, max=25, step=0.5)
                self.max_height = number(
                    "Highest allowed above takeoff (m)",
                    120.0,
                    "max-height-input",
                    "w-72",
                    min=10,
                    max=500,
                )
                self.max_distance = number(
                    "Farthest from takeoff (m)",
                    500.0,
                    "max-distance-input",
                    "w-60",
                    min=50,
                    max=5000,
                )
                self.battery = number(
                    "Flying time per battery (min)", 20.0, "battery-input", "w-64", min=3, max=120
                )
                self.waypoints = number(
                    "Waypoints per mission (DJI Fly)",
                    200,
                    "waypoints-input",
                    "w-64",
                    min=10,
                    max=200,
                )
            ui.label(
                "A long plan is split into missions by the battery time or by the number of "
                "waypoints per mission, whichever comes first. DJI Fly takes at most 200 "
                "waypoints in one mission (it warns above that), so 200 is the most."
            ).classes("text-sm av-muted")
            self._speed_fields()
            self.heading = text(
                "Direction of the flight lines in degrees (empty = automatic)",
                "heading-input",
                width="w-96",
            )
            self.crosshatch = ui.switch(
                "Fly a second set of lines across the first (better 3D, twice the flying)"
            ).mark("crosshatch-switch")
            self.calibrate = ui.switch(
                "Tune height and spacing to the real terrain", value=True
            ).mark("calibrate-switch")
            self.straight = ui.switch("Straight legs between waypoints", value=True).mark(
                "straight-switch"
            )
            for widget in (
                self.shutter,
                self.heading,
                self.crosshatch,
                self.calibrate,
                self.straight,
            ):
                widget.bind_visibility_from(
                    self.scan_type, "value", backward=lambda v: v in AREA_KINDS
                )
