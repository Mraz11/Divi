# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Step 7: what every engine did in this project, and one report of it to keep and share."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.engines import RECORD_FILE
from avispria.app.ui import projects
from avispria.app.ui.after_job import save_record
from avispria.app.ui.files import open_in_browser, open_in_file_manager
from avispria.app.ui.jobs import run_job
from avispria.app.ui.journey import first_screen
from avispria.app.ui.layout import frame
from avispria.core.citation import REQUEST, citation
from avispria.core.pipeline import diagram
from avispria.core.report_text import LIMITS


def _engine_table() -> None:
    found = projects.current()
    stamps = found.engines if found is not None else {}
    rows = [
        {
            "n": s.spec.number,
            "engine": s.spec.name,
            "state": s.label,
            "detail": s.detail,
            "finished": stamps.get(s.spec.key, {}).get("finished", ""),
            "path": first_screen(s.spec.key).path,
        }
        for s in projects.states()
    ]
    columns = [
        {"name": "n", "label": "#", "field": "n", "align": "left"},
        {"name": "engine", "label": "Engine", "field": "engine", "align": "left"},
        {"name": "state", "label": "State", "field": "state", "align": "left"},
        {"name": "detail", "label": "What is there", "field": "detail", "align": "left"},
        {"name": "finished", "label": "Last finished", "field": "finished", "align": "left"},
    ]
    ui.table(columns=columns, rows=rows, row_key="n").classes("w-full").mark("engine-table")


async def report_page() -> None:
    with frame("Report"):
        found = projects.current()
        ui.label(f"Project: {found.name}" if found is not None else "Unnamed project").classes(
            "text-lg font-bold"
        ).mark("report-project")
        ui.label(f"One pipeline: {diagram()}.").classes("text-sm av-muted")
        _engine_table()
        with ui.row().classes("gap-2 items-center"):
            save = ui.button("Make the report", icon="description").props("no-caps size=lg")
            save.mark("save-record")
        box = ui.column().classes("w-full gap-2").mark("record-result")
        ui.label(
            "The report is one file in the maps folder (divi_report.html): the results with their "
            "ranges, pictures of the maps, the methods, the quality checks, how the maps were "
            "made, the limits and the citation. It opens in any browser without the internet; "
            "print it from there to make a PDF. Make it again after any change: it is rewritten "
            "each time."
        ).classes("text-sm av-muted")
        with ui.card().classes("w-full"):
            ui.label("Limits to state with your results").classes("font-bold")
            for text in LIMITS:
                ui.label(f"- {text}").classes("text-sm")
        with ui.card().classes("w-full av-note-info").mark("cite-card"):
            ui.label("How to cite").classes("font-bold")
            ui.label(REQUEST).classes("text-sm")
            ui.label(citation()).classes("text-sm font-mono break-all")

    def show(path: Path, made: bool) -> None:
        box.clear()
        with box:
            label = f"Made: {path}" if made else f"Made earlier: {path}"
            ui.label(label).classes("font-medium break-all")
            with ui.row().classes("gap-2"):
                ui.button(
                    "Open the report", icon="open_in_new", on_click=lambda: open_in_browser(path)
                ).props("no-caps").mark("open-report")
                ui.button(
                    "Open the folder",
                    icon="folder_open",
                    color="secondary",
                    on_click=lambda: open_in_file_manager(path.parent),
                ).props("no-caps")

    async def write() -> None:
        outcome = await run_job(save_record)
        if not outcome.ok or outcome.value is None:
            box.clear()
            with box:
                ui.label(outcome.error or "The report was not made.").classes(
                    "av-problem-text font-medium"
                )
            return
        show(outcome.value, True)

    earlier = projects.links().maps_folder
    if earlier and (Path(earlier) / RECORD_FILE).is_file():
        show(Path(earlier) / RECORD_FILE, False)
    save.on_click(write)
