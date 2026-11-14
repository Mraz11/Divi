# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Continue a processing job that stopped: choose its results folder, see how far it got.

Every job keeps a work record in its results folder (``divi_work.json``). Continuing runs the
same steps again and skips what is already done: the photos are not resized or sent again while
the engine still has them, and results already downloaded are not downloaded again.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.process_work import WORK_FILE
from avispria.app.ui.process_job import ProcessFormError, work_summary
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField

RESUME_HELP = (
    "Choose the results folder of a job that was stopped (with Stop, by closing the window, or "
    "because the computer went off). Dīvi reads what was done from the work record in it "
    f"({WORK_FILE}) and goes on from there, with the same settings. The photos must still be "
    "where they were. If WebODM still has the job, it carries on there; if not, the photos are "
    "sent again."
)


class ResumeSection:
    """The results folder to continue, and what Dīvi knows about it."""

    def __init__(self, job: ui.radio) -> None:
        with ui.column().classes("w-full gap-2") as box:
            ui.label(RESUME_HELP).classes("text-sm av-muted")
            self.folder = PathField(
                "Results folder of the job",
                value=STATE.maps_folder,
                marker="resume",
                on_change=self.show,
            )
            self.status = ui.label().classes("text-sm").mark("resume-status")
        box.bind_visibility_from(job, "value", backward=lambda v: v == "resume")
        self.show()

    def show(self) -> None:
        if not self.folder.value:
            self.status.set_text("")
            return
        try:
            self.status.set_text(work_summary(self.folder.value))
            self.status.classes(add="av-good-text", remove="av-problem-text")
        except ProcessFormError as exc:
            self.status.set_text(str(exc))
            self.status.classes(add="av-problem-text", remove="av-good-text")

    def check(self) -> Path:
        """The folder to continue; ProcessFormError if there is nothing to continue there."""
        work_summary(self.folder.value)
        return Path(self.folder.value).expanduser()


def resume_later(box: ui.column, out_dir: Path) -> None:
    """After a job that did not finish: it can be continued."""
    if not (out_dir / WORK_FILE).is_file():
        return
    with box, ui.card().classes("w-full av-accent-bar").mark("resume-later"):
        ui.label("This job can be continued").classes("font-bold")
        ui.label(
            "Choose 'Continue a job that stopped' at the top of this screen and this results "
            f'folder: {out_dir}. Or, in a terminal: divi resume "{out_dir}"'
        ).classes("text-sm")
