# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the screens remember between each other, and between runs (one person, one computer).

Only file and folder paths are kept, in ``~/Divi/settings.json``; no coordinates and nothing
about a flight's place. Saving starts when ``load`` is called (the program does it at start-up), so
tests and tools that never call it never touch the file.
"""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from avispria.app import project
from avispria.app.paths import app_home
from avispria.core.analyses import KEYS

PERSISTED = (
    "photo_folder",
    "last_output",
    "sample_mission",
    "adb_path",
    "last_plan_files",
    "last_sent_files",
    "maps_folder",
    "project_folder",
    "projects",
    "analyses_off",
)
# what belongs to the project in hand: written through to its record when a project is open
LINKS = {
    "last_plan_files": "plan_files",
    "last_sent_files": "sent_files",
    "photo_folder": "photo_folder",
    "maps_folder": "maps_folder",
}
FILES = ("sample_mission",)  # a path to a file that must still exist to be remembered
FOLDERS = ("photo_folder", "last_output", "maps_folder", "project_folder")
FILE_LISTS = ("last_plan_files", "last_sent_files")


def settings_path() -> Path:
    override = os.environ.get("AVISPRIA_SETTINGS")
    return Path(override) if override else app_home() / "settings.json"


@dataclass
class SharedState:
    photo_folder: str = ""  # last photos checked: pre-fills "Make maps"
    last_output: str = ""  # last output folder: where the folder browser starts
    sample_mission: str = ""  # a mission copied from the phone: pre-fills the Plan screen
    adb_path: str = ""  # where adb is, if it is not found by itself
    last_plan_files: list[str] = field(default_factory=list)  # the last plan's missions
    last_sent_files: list[str] = field(default_factory=list)  # the missions last sent to the phone
    maps_folder: str = ""  # where this project's maps are made
    project_folder: str = ""  # the open project ('' = an unnamed one, kept only in the settings)
    projects: list[str] = field(default_factory=list)
    analyses_off: list[str] = field(
        default_factory=list
    )  # remembered switches (core/analyses)  # folders of the projects made or opened

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name in PERSISTED and self.__dict__.get("_saving", False):
            self.save()
        if name in LINKS and self.__dict__.get("project_folder"):
            self.to_project()

    def links(self) -> dict[str, Any]:
        """The project's links, under the names the project record uses."""
        return {theirs: getattr(self, ours) for ours, theirs in LINKS.items()}

    def to_project(self) -> None:
        """Write the links into the open project's record. Never stops the program."""
        with contextlib.suppress(project.ProjectError):
            project.update_links(Path(self.project_folder), self.links())

    def load(self) -> None:
        """Read the remembered settings (what is gone from disk is forgotten) and start saving."""
        try:
            raw = json.loads(settings_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        for name in PERSISTED:
            value = raw.get(name)
            if name == "analyses_off":
                found = value if isinstance(value, list) else []
                object.__setattr__(self, name, [k for k in KEYS if k in found])
            elif name == "projects":
                found = value if isinstance(value, list) else []
                kept = [p for p in found if isinstance(p, str) and project.is_project(Path(p))]
                object.__setattr__(self, name, kept)
            elif name in FILE_LISTS:
                kept = (
                    [p for p in value if isinstance(p, str) and Path(p).is_file()]
                    if isinstance(value, list)
                    else []
                )
                object.__setattr__(self, name, kept)
            elif isinstance(value, str):
                gone = (name in FILES and not Path(value).is_file()) or (
                    name in FOLDERS and not Path(value).is_dir()
                )
                object.__setattr__(self, name, "" if gone else value)
        object.__setattr__(self, "_saving", True)

    def save(self) -> None:
        data = {name: getattr(self, name) for name in PERSISTED}
        path = settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass  # remembering is a convenience: never stop the program for it


STATE = SharedState()


def reset() -> None:
    object.__setattr__(STATE, "_saving", False)
    object.__setattr__(STATE, "project_folder", "")
    STATE.projects = []
    STATE.photo_folder = ""
    STATE.last_output = ""
    STATE.sample_mission = ""
    STATE.adb_path = ""
    STATE.last_plan_files = []
    STATE.last_sent_files = []
    STATE.maps_folder = ""
    STATE.analyses_off = []
