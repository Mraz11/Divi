# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The projects on the Start page: the one in hand, the others, and how to start or open one."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.project import MANIFEST, ProjectError
from avispria.app.ui import projects
from avispria.app.ui.journey import ask_new_project
from avispria.app.ui.progress import current_progress, project_label
from avispria.app.ui.widgets import PathField

HELP = (
    "A project is one flight campaign: its plan, photos, maps and measurements, with a small "
    f"record of where they are ({MANIFEST}) in a folder of its own. Give a project a name to "
    "keep it in this list and to switch between projects."
)


class ProjectPanel:
    """The project in hand and the list of projects."""

    def __init__(self) -> None:
        with ui.card().classes("w-full gap-2").mark("project-panel"):
            with ui.row().classes("w-full items-center justify-between gap-2"):
                ui.label("Projects").classes("text-lg font-bold")
                with ui.row().classes("gap-2"):
                    ui.button("New project", icon="add", on_click=ask_new_project).props(
                        "no-caps outline"
                    ).mark("new-project")
                    ui.button("Open a project folder", icon="folder_open").props(
                        "no-caps flat"
                    ).mark("open-project").on_click(self._toggle)
            ui.label(project_label(current_progress())).classes("av-muted").mark("project-label")
            with ui.column().classes("w-full gap-2") as self.opener:
                self.folder = PathField(
                    "Project folder",
                    marker="project-folder",
                    hint=f"A folder with a {MANIFEST} file in it.",
                )
                ui.button("Open", on_click=lambda: self._open(self.folder.value)).props(
                    "no-caps"
                ).mark("open-project-confirm")
            self.opener.set_visibility(False)
            self.problem = ui.label("").classes("av-problem-text").mark("project-problem")
            self.problem.set_visibility(False)
            rows = projects.known()
            if not rows:
                ui.label(HELP).classes("text-sm av-muted")
            for n, row in enumerate(rows):
                with ui.row().classes("w-full items-center gap-2 no-wrap").mark(f"project-{n}"):
                    ui.icon("folder_open" if row.open else "folder").classes("text-xl")
                    with ui.column().classes("gap-0 grow"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label(row.name).classes("font-bold")
                            if row.open:
                                ui.badge("Open").props("color=primary")
                        ui.label(f"{row.summary}. Made {row.created}. {row.folder}").classes(
                            "text-xs av-muted break-all"
                        )
                    if not row.open:
                        ui.button("Open", on_click=lambda f=row.folder: self._open(f)).props(
                            "no-caps outline"
                        ).mark(f"project-open-{n}")
                    ui.button(icon="remove", on_click=lambda f=row.folder: self._forget(f)).props(
                        'flat dense aria-label="Take off the list"'
                    ).mark(f"project-forget-{n}").tooltip(
                        "Take off this list. The folder and its files stay on disk."
                    )

    def _toggle(self) -> None:
        self.opener.set_visibility(not self.opener.visible)

    def _open(self, folder: str) -> None:
        if not folder.strip():
            self._say("Choose the project's folder.")
            return
        try:
            projects.open_project(Path(folder.strip()).expanduser())
        except ProjectError as exc:
            self._say(str(exc))
            return
        ui.navigate.to("/")

    def _forget(self, folder: str) -> None:
        projects.forget(folder)
        ui.navigate.to("/")

    def _say(self, text: str) -> None:
        self.problem.set_text(text)
        self.problem.set_visibility(True)
