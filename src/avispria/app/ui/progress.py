# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where a flight project stands, and the one thing to do next.

Worked out from what the screens remember (the sample mission, the last plan, what was sent, the
photos checked), so a person never has to guess which step comes next.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from avispria.app.ui import projects
from avispria.app.ui.state import STATE
from avispria.core.pipeline import TOTAL


@dataclass(frozen=True)
class Progress:
    has_sample: bool = False
    planned: int = 0  # missions in the last plan that are still on disk
    sent: int = 0  # missions last sent to the phone
    checked: bool = False  # photos have been checked
    maps: bool = False  # maps were made for this project
    cut: bool = False  # the maps were cut to the study area (optional)
    measured: bool = False  # canopy, trees and cover were measured
    exported: bool = False  # files were exported for QGIS
    reported: bool = False  # the report was made
    name: str = ""  # the open project's name ('' = unnamed)
    started: datetime | None = None  # when this project's plan was made

    @property
    def any(self) -> bool:
        return bool(self.planned or self.sent or self.checked or self.maps)


@dataclass(frozen=True)
class NextAction:
    step: int  # 0 = the one-time set-up, else the step of the journey
    title: str
    text: str
    path: str = ""  # where the button goes ('' = the action is on this screen)
    button: str = ""


def _present(paths: list[str]) -> int:
    return sum(1 for p in paths if Path(p).is_file())


def current_progress() -> Progress:
    done = {s.spec.key for s in projects.states() if s.done}
    found = projects.current()
    return Progress(
        has_sample=bool(STATE.sample_mission) and Path(STATE.sample_mission).is_file(),
        planned=_present(STATE.last_plan_files),
        sent=len(STATE.last_sent_files),
        checked="photos" in done,
        maps="reconstruct" in done,
        cut="map" in done,
        measured="analyse" in done,
        exported="export" in done,
        reported="report" in done,
        name=found.name if found is not None else "",
        started=_started(STATE.last_plan_files),
    )


def _started(paths: list[str]) -> datetime | None:
    times = [Path(p).stat().st_mtime for p in paths if Path(p).is_file()]
    return datetime.fromtimestamp(min(times)) if times else None


def project_label(p: Progress) -> str:
    """One line naming the project in hand, so an old one is recognised as old."""
    title = f"Project {p.name}" if p.name else "Current flight project"
    if not p.any:
        return f"{title}: nothing done yet." if p.name else "No flight project yet."
    when = f"planned {p.started:%d %b %Y, %H:%M}" if p.started else "plan files no longer found"
    done = sum(step_done(n, p) for n in range(1, TOTAL + 1))
    return f"{title}: {when}; {done} of {TOTAL} steps done."


def new_project() -> None:
    """Start the next flight: forget this project's plan, sending, photos and maps.

    Nothing is deleted from disk, and the one-time set-up (the sample mission, adb, the output
    folder) is kept.
    """
    projects.close_project()


def step_done(number: int, p: Progress) -> bool:
    """Is an engine of the pipeline done? (numbers as in ``core/pipeline.py``)"""
    return {
        1: p.planned > 0,
        2: p.sent > 0,
        3: p.checked,
        4: p.maps,
        5: p.cut,
        6: p.measured,
        7: p.exported,
        8: p.reported,
    }.get(number, False)


def _missions(n: int) -> str:
    return f"{n} mission{'s' if n != 1 else ''}"


def next_action(p: Progress) -> NextAction:
    if not p.has_sample:
        return NextAction(
            0,
            "First, once: get your sample mission from the phone",
            "Dīvi needs one mission made by DJI Fly, to copy the exact format of your "
            "aircraft. You do this once; it is remembered.",
        )
    if p.planned == 0:
        return NextAction(
            1,
            "Plan your flight",
            "Choose what you want to capture, mark the place, and get missions for DJI Fly.",
            "/plan",
            "Start: 1. Plan a flight",
        )
    if p.sent == 0:
        return NextAction(
            2,
            f"Send your {_missions(p.planned)} to DJI Fly",
            "Put the missions into DJI Fly on your phone. The screen tells you if more "
            "placeholder missions are needed first.",
            "/phone",
            "Next: 2. Send to DJI Fly",
        )
    if not p.checked:
        return NextAction(
            3,
            "Fly, then check your photos",
            "Fly the missions in DJI Fly. After landing, copy the photos to this computer and "
            "check them.",
            "/fly",
            "Open the flight checklist",
        )
    if not p.maps:
        return NextAction(
            4,
            "Make your map or 3D model",
            "Your photos are checked. Turn them into a map or a model with WebODM, on this "
            "computer.",
            "/process",
            "Next: 4. Make maps",
        )
    if not p.measured:
        return NextAction(
            6,
            "Measure your maps",
            "Your maps are made. Measure canopy height, trees and cover from them. Cutting the "
            "maps to your study area first (step 5) is optional.",
            "/analyse",
            "Next: 6. Measure",
        )
    if not p.exported:
        return NextAction(
            7,
            "Export for QGIS",
            "Everything is measured. Save the maps and measurements as files for QGIS and "
            "other programs, one file per band, and make map images.",
            "/export",
            "Next: 7. Export",
        )
    if not p.reported:
        return NextAction(
            8,
            "Make the report",
            "Everything is exported. Make one report of what was done, with which settings and "
            "versions, and how to cite it.",
            "/report",
            "Next: 8. Report",
        )
    return NextAction(
        9,
        "This flight project is finished",
        "Maps, measurements and the report are made. To fly somewhere else, start a new "
        "project: the plan, photos and maps of this one stay on disk.",
        "/report",
        "See the report",
    )
