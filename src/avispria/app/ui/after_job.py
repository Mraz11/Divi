# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Map, Analyse and Report engines run on their own, on maps that are already made.

Each function takes what the screen holds as plain text and numbers, checks it, runs the engine
through ``engines.runner`` and records in the open project that it finished. Every rule is tested
without a browser.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from rasterio.errors import RasterioIOError

from avispria.app.canopy_workflow import CanopyError
from avispria.app.clip_workflow import ClipError, ClipOutcome, restore_uncut
from avispria.app.engines import runner
from avispria.app.export_rasters import ExportError
from avispria.app.export_workflow import ExportOptions, ExportOutcome
from avispria.app.inventory_files import InventoryError
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.paths import provenance_file
from avispria.app.report_workflow import ReportError
from avispria.app.ui import projects
from avispria.app.ui.process_job import ProcessFormError, _check_trees, _clip_file
from avispria.core.profiles import PROFILES

DSM = "odm_dem/dsm.tif"


class AfterError(ValueError):
    """The engine could not run; the message says what to change."""


def maps_folder(text: str) -> Path:
    """The maps folder (the one with ``results`` in it) from what was typed; raises AfterError."""
    if not text.strip():
        raise AfterError("Choose the folder where your maps were saved.")
    folder = Path(text.strip()).expanduser()
    if folder.name == "results" and not (folder / "results").is_dir():
        folder = folder.parent  # the results folder itself was chosen: one level up
    if not (folder / "results").is_dir():
        raise AfterError(
            f"There are no maps in {folder}. Choose the folder that 'Make maps' saved to "
            "(it has a 'results' folder inside)."
        )
    return folder


def read_provenance(folder: Path) -> Mapping[str, Any]:
    try:
        found = json.loads(provenance_file(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, Mapping) else {}


def run_cut(folder_text: str, file_text: str, buffer_m: float) -> ClipOutcome:
    """Cut the maps in a folder to an area; the uncut maps are kept."""
    folder = maps_folder(folder_text)
    try:
        mask = _clip_file(file_text)
    except ProcessFormError as exc:
        raise AfterError(str(exc)) from None
    if mask is None:
        raise AfterError("Choose the file with the area to cut the maps by.")
    try:
        outcome: ClipOutcome = runner("map")(folder / "results", mask, max(0.0, buffer_m))
    except ClipError as exc:
        raise AfterError(f"The maps were not cut: {exc}") from None
    projects.stamp("map", f"cut by {mask.name}")
    return outcome


def undo_cut(folder_text: str) -> list[Path]:
    """Put the uncut maps back."""
    folder = maps_folder(folder_text)
    restored = restore_uncut(folder / "results")
    if not restored:
        raise AfterError("These maps are not cut: there is nothing to undo.")
    return restored


def run_measure(folder_text: str, profile: str, trees: TreeInputs) -> dict[str, Any]:
    """Measure the maps in a folder again; returns the canopy numbers for the screen."""
    folder = maps_folder(folder_text)
    if profile not in PROFILES:
        raise AfterError("Choose what you mapped from the list.")
    if not (folder / "results" / DSM).is_file():
        raise AfterError(
            "These maps have no surface model, so nothing can be measured. Make the maps again "
            "with the Standard or Detailed quality."
        )
    try:
        checked = _check_trees(trees)
        outcome = runner("analyse")(folder / "results", profile, trees=checked)
    except ProcessFormError as exc:
        raise AfterError(str(exc)) from None
    except (CanopyError, InventoryError, RasterioIOError) as exc:
        raise AfterError(f"The maps could not be measured: {exc}") from None
    projects.stamp("analyse", profile)
    return {"canopy": asdict(outcome.canopy.stats)}


def save_record() -> Path:
    """Write the report of the project in hand into its maps folder."""
    found = projects.current()
    name = found.name if found is not None else ""
    stamps = dict(found.engines) if found is not None else {}
    try:
        path: Path = runner("report")(projects.links(), name, stamps)
    except ReportError as exc:
        raise AfterError(str(exc)) from None
    projects.stamp("report")
    return path


def run_export_job(folder_text: str, options: ExportOptions) -> ExportOutcome:
    """Export the maps in a folder for QGIS; records that the Export engine finished."""
    folder = maps_folder(folder_text)
    try:
        outcome: ExportOutcome = runner("export")(folder, options)
    except ExportError as exc:
        raise AfterError(f"Nothing was exported: {exc}") from None
    projects.stamp("export", f"{len(outcome.files)} files")
    return outcome
