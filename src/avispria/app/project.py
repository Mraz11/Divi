# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A project: one folder with a small record (``divi_project.json``) of where its files are.

The record holds a name, dates, the Dīvi version and file and folder paths: the missions of the
plan, what was sent to the phone, the photo folder and the maps folder. It never holds
coordinates. Paths inside the project folder are written relative to it, so the folder can be
moved or copied to another computer and continued there.

The state of each engine is not stored: it is read from what is on disk (``engines.inspect``).
What is stored per engine is only when it last finished and with which version.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from avispria.app.paths import app_home
from avispria.core.pipeline import KEYS
from avispria.core.version import __version__

MANIFEST = "divi_project.json"
FORMAT = 1
LINK_LISTS = ("plan_files", "sent_files")
LINK_FOLDERS = ("photo_folder", "maps_folder")
LINKS = (*LINK_LISTS, *LINK_FOLDERS)
ENGINE_OF_LINK = {
    "plan_files": "plan",
    "sent_files": "mission",
    "photo_folder": "photos",
    "maps_folder": "reconstruct",
}


class ProjectError(ValueError):
    """The project folder or its record cannot be used; the message says why."""


@dataclass
class Project:
    folder: Path
    name: str
    created: str = ""
    plan_files: list[str] = field(default_factory=list)
    sent_files: list[str] = field(default_factory=list)
    photo_folder: str = ""
    maps_folder: str = ""
    engines: dict[str, dict[str, str]] = field(default_factory=dict)  # when and which version
    version: str = __version__

    def links(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in LINKS}


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime())


def manifest(folder: Path) -> Path:
    return folder / MANIFEST


def is_project(folder: Path) -> bool:
    return manifest(folder).is_file()


def default_root() -> Path:
    """Where new projects are made unless another folder is chosen: ``~/Divi/projects``."""
    return app_home() / "projects"


def slug(name: str) -> str:
    """A folder name from a project name, in any script: only what no file system allows goes."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f\s]+', "-", name).strip("-_. ")
    return cleaned[:60].rstrip("-_. ") or "project"


def _store(path: str, folder: Path) -> str:
    """Relative to the project folder when inside it, so the folder can be moved."""
    if not path:
        return ""
    full = Path(path).absolute()
    try:
        return full.resolve().relative_to(folder.resolve()).as_posix()
    except ValueError:
        return str(full)


def _restore(path: str, folder: Path) -> str:
    if not path:
        return ""
    found = Path(path)
    return str(found if found.is_absolute() else folder / found)


def save_project(project: Project) -> None:
    """Write the record; a half-written file never replaces a good one."""
    folder = project.folder
    data = asdict(project) | {"format": FORMAT, "version": __version__}
    del data["folder"]
    for name in LINK_LISTS:
        data[name] = [_store(p, folder) for p in getattr(project, name)]
    for name in LINK_FOLDERS:
        data[name] = _store(getattr(project, name), folder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        part = manifest(folder).with_suffix(".part")
        part.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        part.replace(manifest(folder))
    except OSError as exc:
        raise ProjectError(f"The project record could not be written in {folder}: {exc}") from None


def load_project(folder: Path) -> Project:
    if not is_project(folder):
        raise ProjectError(f"There is no Dīvi project ({MANIFEST}) in {folder}.")
    try:
        raw = json.loads(manifest(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"The project record in {folder} could not be read: {exc}") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
        raise ProjectError(f"The project record in {folder} is not a Dīvi project record.")
    engines = raw.get("engines")
    project = Project(
        folder=folder,
        name=raw["name"],
        created=str(raw.get("created", "")),
        engines={
            k: {str(a): str(b) for a, b in v.items()}
            for k, v in (engines.items() if isinstance(engines, dict) else ())
            if k in KEYS and isinstance(v, dict)
        },
        version=str(raw.get("version", "")),
    )
    for name in LINK_LISTS:
        value = raw.get(name)
        items = value if isinstance(value, list) else []
        setattr(project, name, [_restore(p, folder) for p in items if isinstance(p, str)])
    for name in LINK_FOLDERS:
        value = raw.get(name)
        setattr(project, name, _restore(value, folder) if isinstance(value, str) else "")
    return project


def create_project(folder: Path, name: str) -> Project:
    """A new project in ``folder`` (made if needed); never replaces an existing project."""
    if not name.strip():
        raise ProjectError("Give the project a name.")
    if folder.is_file():
        raise ProjectError(f"That is a file, not a folder: {folder}")
    if is_project(folder):
        raise ProjectError(f"There is already a project in {folder}. Open it instead.")
    project = Project(folder=folder, name=name.strip(), created=now())
    save_project(project)
    return project


def free_folder(root: Path, name: str) -> Path:
    """``root/<name>``, or with -2, -3... if a project of that name is already there."""
    base = slug(name)
    for n in range(1, 1000):
        folder = root / (base if n == 1 else f"{base}-{n}")
        if not folder.exists():
            return folder
    raise ProjectError(f"Too many projects called {name!r} in {root}.")


def stamp(project: Project, key: str, note: str = "") -> None:
    """Record that an engine finished now, with this version."""
    if key not in KEYS:
        raise ProjectError(f"no engine called {key!r}")
    entry = {"finished": now(), "version": __version__}
    if note:
        entry["note"] = note
    project.engines[key] = entry


def update_links(folder: Path, links: dict[str, Any]) -> Project:
    """Write changed links into the project in ``folder``, stamping the engines they belong to."""
    project = load_project(folder)
    for name in LINKS:
        if name not in links or links[name] == getattr(project, name):
            continue
        setattr(project, name, links[name])
        if links[name]:
            stamp(project, ENGINE_OF_LINK[name])
        else:
            project.engines.pop(ENGINE_OF_LINK[name], None)
    save_project(project)
    return project
