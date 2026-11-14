# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The project in hand, and the list of projects: what the screens need from ``app/project.py``.

Without an open project the links live only in the settings (an "unnamed project"), as before
projects had folders. Opening or starting a project swaps the links for that project's own.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path

from avispria.app import project as store
from avispria.app.engines import EngineState, Links, inspect
from avispria.app.project import Project, ProjectError
from avispria.app.ui import drafts
from avispria.app.ui.state import LINKS, STATE
from avispria.core.pipeline import TOTAL


@dataclass(frozen=True)
class ProjectRow:
    folder: str
    name: str
    created: str
    done: int  # engines finished, of TOTAL
    open: bool
    summary: str


def links() -> Links:
    return Links(
        tuple(STATE.last_plan_files),
        tuple(STATE.last_sent_files),
        STATE.photo_folder,
        STATE.maps_folder,
    )


def states() -> tuple[EngineState, ...]:
    """Where every engine of the project in hand stands."""
    return inspect(links())


def state_of(key: str) -> EngineState:
    return next(s for s in states() if s.spec.key == key)


def current() -> Project | None:
    """The open project, or None for an unnamed one (or if its folder is gone)."""
    if not STATE.project_folder:
        return None
    try:
        return store.load_project(Path(STATE.project_folder))
    except ProjectError:
        return None


def _set_links(values: dict[str, object]) -> None:
    """Put a project's links on the screens without writing them back to a project."""
    folder = STATE.project_folder
    object.__setattr__(STATE, "project_folder", "")
    for ours, theirs in LINKS.items():
        setattr(STATE, ours, values.get(theirs) or ([] if ours.endswith("_files") else ""))
    object.__setattr__(STATE, "project_folder", folder)


def close_project() -> None:
    """Back to an empty, unnamed project. Nothing is deleted."""
    STATE.project_folder = ""
    _set_links({})
    drafts.forget()


def open_project(folder: Path) -> Project:
    """Make the project in ``folder`` the one in hand; raises ProjectError."""
    found = store.load_project(folder)
    STATE.project_folder = ""
    _set_links(found.links())
    drafts.forget()
    STATE.project_folder = str(folder)
    if str(folder) not in STATE.projects:
        STATE.projects = [*STATE.projects, str(folder)]
    return found


def start_project(name: str, root: Path | None = None) -> Project:
    """A new, empty project called ``name`` in its own folder, opened; raises ProjectError."""
    if not name.strip():
        raise ProjectError("Give the project a name.")
    base = root or store.default_root()
    made = store.create_project(store.free_folder(base, name), name)
    return open_project(made.folder)


def stamp(key: str, note: str = "") -> None:
    """Record in the open project that an engine finished now (nothing to do if unnamed)."""
    found = current()
    if found is not None:
        store.stamp(found, key, note)
        with contextlib.suppress(ProjectError):
            store.save_project(found)


def forget(folder: str) -> None:
    """Take a project off the list. Its folder and files stay on disk."""
    STATE.projects = [p for p in STATE.projects if p != folder]
    if STATE.project_folder == folder:
        close_project()


def known() -> list[ProjectRow]:
    """The projects made or opened on this computer that are still on disk, newest first."""
    rows = []
    for folder in STATE.projects:
        try:
            found = store.load_project(Path(folder))
        except ProjectError:
            continue
        found_states = inspect(
            Links(
                tuple(found.plan_files),
                tuple(found.sent_files),
                found.photo_folder,
                found.maps_folder,
            )
        )
        done = sum(1 for s in found_states if s.done)
        rows.append(
            ProjectRow(
                folder,
                found.name,
                found.created,
                done,
                folder == STATE.project_folder,
                f"{done} of {TOTAL} steps done",
            )
        )
    return sorted(rows, key=lambda r: r.created, reverse=True)
