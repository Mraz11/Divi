# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Make maps form as plain data, and what it takes to check and run the job.

The screen fills in a ``ProcessForm`` and draws what these functions return; every rule
(defaults, validation, what a blocked job looks like) is tested without a browser.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from avispria.adapters.area_file import SUFFIXES as AREA_SUFFIXES
from avispria.app.doctor import DoctorReport, run_doctor
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.process_work import WorkError, load_work
from avispria.app.process_workflow import (
    ProcessBlockedError,
    ProcessOutcome,
    ProcessRequest,
    Reporter,
    request_from_work,
    run_process,
    task_name,
)
from avispria.app.ui.files import start_folder
from avispria.core.feasibility import Assessment
from avispria.core.processing import PRESETS

PHOTO_SIZES = {
    "12.2": "12 MP (recommended)",
    "8": "8 MP (less memory)",
    "6": "6 MP (much less memory)",
    "4": "4 MP (for small computers)",
    "3": "3 MP (for very small computers)",
    "full": "Full size (needs a lot of memory)",
}
FULL_SIZE_MP = 1e9  # "no limit" when asking the computer check


class ProcessFormError(ValueError):
    """Something in the form is missing or wrong; the message says what to change."""


@dataclass(frozen=True)
class ProcessForm:
    folder: str = ""
    out_dir: str = ""  # empty: next to the photo folder, see default_output
    preset: str = "standard"
    recursive: bool = False
    photo_size: str = "12.2"  # a key of PHOTO_SIZES
    force: bool = False  # start even if this computer looks too small
    keep_repeats: bool = False  # also send photos taken while hovering or in a repeated pass
    profile: str = "forest"  # what was mapped (core/profiles.py)
    engine_url: str = ""  # empty: find WebODM's engine by itself
    engine_token: str = ""  # empty: read from the running engine, or none needed
    trees: TreeInputs = field(default_factory=TreeInputs)  # optional inputs of the inventory
    clip_file: str = ""  # cut the stitched maps to this area; empty: not cut
    clip_buffer_m: float = 0.0


@dataclass(frozen=True)
class ProcessJobResult:
    outcome: ProcessOutcome | None = None
    provenance: dict[str, Any] | None = None
    blocked: str | None = None
    assessment: Assessment | None = None


def default_output(folder: str) -> str:
    """A new folder next to the photos, named after the survey (empty if no folder yet)."""
    if not folder.strip():
        return ""
    path = Path(folder.strip()).expanduser()
    return str(path.parent / f"{task_name(path)}_avispria")


def _photo_size_mp(form: ProcessForm) -> float | None:
    if form.photo_size == "full":
        return None
    try:
        return float(form.photo_size)
    except ValueError:
        raise ProcessFormError("Choose one of the photo sizes in the list.") from None


def build_request(form: ProcessForm, cancel: threading.Event | None = None) -> ProcessRequest:
    """Validate the form and make the processing request."""
    if not form.folder.strip():
        raise ProcessFormError("Choose the folder with your photos.")
    folder = Path(form.folder.strip()).expanduser()
    if not folder.is_dir():
        raise ProcessFormError(f"That photo folder does not exist: {folder}")
    if form.preset not in PRESETS:
        raise ProcessFormError("Choose one of the quality levels in the list.")
    out_dir = Path(form.out_dir.strip() or default_output(form.folder)).expanduser()
    if out_dir.is_file():
        raise ProcessFormError(f"That is a file, not a folder: {out_dir}")
    if out_dir.resolve().is_relative_to(folder.resolve()):
        raise ProcessFormError(
            "Save the results outside the photo folder, so they are never mistaken for photos."
        )
    engine_url = form.engine_url.strip()
    if engine_url and not engine_url.lower().startswith(("http://", "https://")):
        raise ProcessFormError(
            "The engine address should look like http://localhost:3000 (starting with http://)."
        )
    return ProcessRequest(
        folder=folder,
        out_dir=out_dir,
        preset=form.preset,  # type: ignore[arg-type]
        recursive=form.recursive,
        resize_mp=_photo_size_mp(form),
        force=form.force,
        keep_repeats=form.keep_repeats,
        profile=form.profile,
        url=engine_url or None,
        token=form.engine_token.strip() or None,
        cancel=cancel,
        trees=_check_trees(form.trees),
        clip_file=_clip_file(form.clip_file),
        clip_buffer_m=max(0.0, float(form.clip_buffer_m or 0.0)),
    )


def _clip_file(text: str) -> Path | None:
    if not text.strip():
        return None
    path = Path(text.strip()).expanduser()
    if not path.is_file():
        raise ProcessFormError(f"The area to cut the maps by was not found: {path}")
    if path.suffix.lower() not in AREA_SUFFIXES:
        raise ProcessFormError(
            f"Cut by a {', '.join(AREA_SUFFIXES)} file, not {path.suffix or 'this file'}."
        )
    return path


def _check_trees(trees: TreeInputs) -> TreeInputs:
    for label, path in (
        ("ground model from elsewhere", trees.ground_file),
        ("independent ground model", trees.reference_file),
        ("file of trees measured on the ground", trees.field_heights),
    ):
        if path is not None and not path.is_file():
            raise ProcessFormError(f"The {label} was not found: {path}")
    if trees.ground_file is not None and trees.ground_file == trees.reference_file:
        raise ProcessFormError(
            "The doming check needs a ground model other than the one used for the heights."
        )
    return trees


def check_computer(form: ProcessForm) -> DoctorReport:
    """Can this computer do this job? (the same check as `avispria doctor <folder>`)."""
    request = build_request(form)
    mp = FULL_SIZE_MP if request.resize_mp is None else request.resize_mp
    return run_doctor(
        start_folder(request.out_dir), request.folder, recursive=request.recursive, processing_mp=mp
    )


def _work_dir(text: str) -> Path:
    if not text.strip():
        raise ProcessFormError("Choose the results folder of the job to continue.")
    path = Path(text.strip()).expanduser()
    if not path.is_dir():
        raise ProcessFormError(f"That folder does not exist: {path}")
    return path


def work_summary(text: str) -> str:
    """What the job in this results folder is, and how far it got."""
    try:
        record = load_work(_work_dir(text))
    except WorkError as exc:
        raise ProcessFormError(str(exc)) from None
    return f"Photos: {record.folder}. {record.describe()}"


def execute_resume(
    folder_text: str,
    token: str,
    force: bool,
    reporter: Reporter,
    cancel: threading.Event | None = None,
) -> ProcessJobResult:
    """Continue the job in a results folder, from where it stopped."""
    try:
        request = request_from_work(
            _work_dir(folder_text), token=token.strip() or None, cancel=cancel, force=force
        )
    except WorkError as exc:
        raise ProcessFormError(str(exc)) from None
    return _run(request, reporter)


def execute_process(
    form: ProcessForm, reporter: Reporter, cancel: threading.Event | None = None
) -> ProcessJobResult:
    """Run the job; a job that could not start comes back with the reason and alternatives."""
    return _run(build_request(form, cancel), reporter)


def _run(request: ProcessRequest, reporter: Reporter) -> ProcessJobResult:
    try:
        outcome = run_process(request, reporter)
    except ProcessBlockedError as exc:
        return ProcessJobResult(blocked=str(exc), assessment=exc.assessment)
    provenance = json.loads(outcome.provenance_path.read_text(encoding="utf-8"))
    return ProcessJobResult(outcome=outcome, provenance=provenance)
