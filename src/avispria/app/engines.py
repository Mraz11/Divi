# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The engines of the pipeline (``core/pipeline.py``): how each is run, and where it stands.

``RUN`` names the one function that does each engine's work; the screens and the command line
both go through it. ``inspect`` reads a project's state from what is on disk, so nothing has to
be remembered: a results folder copied from another computer shows the right state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from avispria.app.clip_workflow import FULL_SUFFIX, PRODUCTS, clip_results
from avispria.app.paths import provenance_file
from avispria.app.process_work import WorkError, load_work, work_file
from avispria.core.pipeline import ENGINES, STATUS_TEXT, EngineSpec, Status, complete, status

EXPORT_FILE = "export/export_manifest.json"  # the Export engine's mark that it finished
RECORD_FILE = "divi_report.html"  # the Report engine's product, in the maps folder
ORTHO = "odm_orthophoto/odm_orthophoto.tif"
ANALYSIS_FILES = ("analysis/surface_summary.json", "canopy/canopy_summary.json")


@dataclass(frozen=True)
class Links:
    """Where a project's files are: all an engine needs to know to say where it stands."""

    plan_files: tuple[str, ...] = ()
    sent_files: tuple[str, ...] = ()
    photo_folder: str = ""
    maps_folder: str = ""

    @property
    def results(self) -> Path | None:
        return Path(self.maps_folder) / "results" if self.maps_folder else None


@dataclass(frozen=True)
class EngineState:
    spec: EngineSpec
    status: Status
    detail: str  # one line: what is there, or what is missing

    @property
    def done(self) -> bool:
        return self.status == "done"

    @property
    def label(self) -> str:
        return STATUS_TEXT[self.status]


def _count(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def _plan(links: Links) -> tuple[bool, bool, str]:
    n = sum(1 for p in links.plan_files if Path(p).is_file())
    return n > 0, False, f"{_count(n, 'mission')} planned" if n else "No plan yet"


def _mission(links: Links) -> tuple[bool, bool, str]:
    n = len(links.sent_files)
    return n > 0, False, f"{_count(n, 'mission')} sent to the phone" if n else "Nothing sent yet"


def _photos(links: Links) -> tuple[bool, bool, str]:
    ok = bool(links.photo_folder) and Path(links.photo_folder).is_dir()
    return ok, False, f"Photos checked: {links.photo_folder}" if ok else "No photos checked yet"


def _reconstruct(links: Links) -> tuple[bool, bool, str]:
    if not links.maps_folder or not Path(links.maps_folder).is_dir():
        return False, False, "No maps made yet"
    folder = Path(links.maps_folder)
    if work_file(folder).is_file():
        try:
            record = load_work(folder)
        except WorkError:
            return False, True, "The work record could not be read"
        if record.step != "done":
            return False, True, record.describe()
    return True, False, f"Maps made: {folder}"


def _map(links: Links) -> tuple[bool, bool, str]:
    results = links.results
    cut = results is not None and any(
        (results / (name[: -len(".tif")] + FULL_SUFFIX)).is_file() for name in PRODUCTS
    )
    return cut, False, "Maps cut to your area" if cut else "Maps not cut (optional)"


def _analyse(links: Links) -> tuple[bool, bool, str]:
    results = links.results
    found = results is not None and any((results / name).is_file() for name in ANALYSIS_FILES)
    return found, False, "Measurements made" if found else "Nothing measured yet"


def _export(links: Links) -> tuple[bool, bool, str]:
    done = bool(links.maps_folder) and (Path(links.maps_folder) / EXPORT_FILE).is_file()
    return done, False, "Files exported for QGIS" if done else "Nothing exported yet"


def _report(links: Links) -> tuple[bool, bool, str]:
    saved = bool(links.maps_folder) and (Path(links.maps_folder) / RECORD_FILE).is_file()
    return saved, False, "Report made" if saved else "No report yet"


INSPECT: dict[str, Callable[[Links], tuple[bool, bool, str]]] = {
    "plan": _plan,
    "mission": _mission,
    "photos": _photos,
    "reconstruct": _reconstruct,
    "map": _map,
    "analyse": _analyse,
    "export": _export,
    "report": _report,
}


def inspect(links: Links) -> tuple[EngineState, ...]:
    """Where every engine stands, in pipeline order."""
    found = {key: INSPECT[key](links) for key in INSPECT}
    done = {key for key, (finished, _, _) in found.items() if finished}
    states = []
    for spec in ENGINES:
        finished, started, detail = found[spec.key]
        states.append(
            EngineState(
                spec, status(spec.key, finished=finished, started=started, done=done), detail
            )
        )
    return tuple(states)


def finished(states: tuple[EngineState, ...]) -> bool:
    return complete({s.spec.key for s in states if s.done})


def has_results(links: Links) -> bool:
    """Is there a stitched map to cut, measure or report on?"""
    results = links.results
    return results is not None and (
        (results / ORTHO).is_file() or provenance_file(Path(links.maps_folder)).is_file()
    )


def _run_table() -> dict[str, Callable[..., Any]]:
    """Each engine's one way in. Imported late: the workflows are heavy and import each other."""
    from avispria.app.capture_workflow import run_qa
    from avispria.app.export_workflow import run_export
    from avispria.app.phone_workflow import send_mission
    from avispria.app.process_workflow import run_process
    from avispria.app.report_workflow import write_record
    from avispria.app.surface_workflow import run_analysis
    from avispria.app.workflow import run_plan

    return {
        "plan": run_plan,
        "mission": send_mission,
        "photos": run_qa,
        "reconstruct": run_process,
        "map": clip_results,
        "analyse": run_analysis,
        "export": run_export,
        "report": write_record,
    }


def runner(key: str) -> Callable[..., Any]:
    """The function that does an engine's work."""
    return _run_table()[key]
