# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make maps: turn a folder of photos into an orthophoto, surface model and point cloud."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from nicegui import ui

from avispria.app.process_work import work_file
from avispria.app.ui.drafts import keep
from avispria.app.ui.jobs import QueueReporter, run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.pages.analysis_switches import SwitchSection
from avispria.app.ui.pages.plan_form_parts import select_fit
from avispria.app.ui.pages.process_progress import ProgressPanel
from avispria.app.ui.pages.process_results import show_feasibility, show_result
from avispria.app.ui.pages.process_resume import ResumeSection, resume_later
from avispria.app.ui.pages.process_trees import ClipSection, TreeSection
from avispria.app.ui.process_job import (
    PHOTO_SIZES,
    ProcessForm,
    ProcessFormError,
    build_request,
    check_computer,
    default_output,
    execute_process,
    execute_resume,
)
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField
from avispria.core.profiles import PROFILES

PRESET_TEXT = {
    "fast": "Fast: the map only, quickest and needs the least memory",
    "standard": "Standard: the map, a surface model and a point cloud (recommended)",
    "detailed": "Detailed: adds a terrain model and a denser point cloud (slower)",
}


def _problem(box: ui.column, text: str) -> None:
    with box:
        ui.label(text).classes("av-problem-text font-medium")


async def process_page() -> None:
    cancel = threading.Event()
    suggested = {"out": ""}
    with frame("Make maps"):
        ui.label(
            "Turn your photos into an orthophoto (a map made of your photos), a surface model "
            "and a point cloud. This uses WebODM on this computer, so WebODM must be running. "
            "Nothing is uploaded to the internet."
        ).classes("text-base")

        def folder_changed() -> None:
            wanted = default_output(folder.value)
            if not out.value or out.value == suggested["out"]:
                out.set(wanted)
                suggested["out"] = wanted

        job = (
            ui.radio(
                {"new": "Make maps from photos", "resume": "Continue a job that stopped"},
                value="new",
            )
            .props("inline")
            .mark("job-kind")
        )
        with ui.column().classes("w-full gap-3") as new_box:
            folder = PathField(
                "Photo folder",
                value=STATE.photo_folder,
                marker="photos",
                on_change=folder_changed,
                hint="Use the original photos from your drone.",
            )
            recursive = ui.switch("Include photos in subfolders").mark("recursive-switch")
            out = PathField(
                "Where to save the results",
                marker="out",
                value=default_output(STATE.photo_folder),
                hint="A new folder is made. Results can be several gigabytes.",
            )
            suggested["out"] = out.value
            preset = ui.radio(PRESET_TEXT, value="standard").mark("preset-radio")
            with (
                ui.expansion("Advanced", icon="tune").classes("w-full border"),
                ui.column().classes("gap-2 p-2"),
            ):
                size = (
                    ui.select(PHOTO_SIZES, value="12.2", label="Photo size for processing")
                    .props("outlined dense")
                    .classes("w-80")
                    .mark("size-select")
                )
                select_fit(size, "Photo size for processing")
                ui.label(
                    "Smaller photos need much less memory and time, at the cost of some detail. "
                    "12 MP is the usual choice."
                ).classes("text-xs av-muted")
                force = ui.switch("Start even if this computer looks too small").mark(
                    "force-switch"
                )
                mapped = (
                    ui.select(
                        {name: p.title for name, p in PROFILES.items()},
                        value="forest",
                        label="What did you map? (decides what is measured)",
                    )
                    .classes("w-80")
                    .mark("profile-select")
                )
                select_fit(mapped, "What did you map? (decides what is measured)")
                repeats = ui.switch(
                    "Use every photo (also those taken while hovering, or in a second pass over "
                    "the same ground)"
                ).mark("repeats-switch")
                ui.label(
                    "Engine: leave these empty and Dīvi finds WebODM's engine by itself (the "
                    "Windows app, or the Docker version at http://localhost:3000). Fill them in "
                    "only for an engine somewhere else. An engine on another computer receives "
                    "all your photos: use an https address, or a network you trust."
                ).classes("text-xs av-muted")
                engine_url = (
                    ui.input("Engine address (optional)", placeholder="http://localhost:3000")
                    .props("outlined dense")
                    .classes("w-80")
                    .mark("engine-url-input")
                )
                engine_token = (
                    ui.input("Engine access token (optional)")
                    .props("outlined dense type=password")
                    .classes("w-80")
                    .mark("engine-token-input")
                )
        with new_box:
            clip_part = ClipSection()
            switch_part = SwitchSection()
            trees_part = TreeSection()
        new_box.bind_visibility_from(job, "value", backward=lambda v: v == "new")
        resume_part = ResumeSection(job)
        keep(
            "process",
            SimpleNamespace(
                folder=folder,
                recursive=recursive,
                out=out,
                preset=preset,
                size=size,
                force=force,
                repeats=repeats,
                mapped=mapped,
                engine_url=engine_url,
            ),
        )
        with ui.row().classes("gap-2 items-center"):
            check_button = (
                ui.button("Check this computer for this job", icon="memory", color="secondary")
                .props("no-caps")
                .mark("check-button")
            )
            start_button = (
                ui.button("Start making maps", icon="play_arrow")
                .props("no-caps size=lg")
                .mark("start-button")
            )
            cancel_button = (
                ui.button("Cancel", icon="stop", color="negative")
                .props("no-caps")
                .mark("cancel-button")
            )
            cancel_button.set_visibility(False)
            for button in (check_button, start_button):
                button.bind_visibility_from(job, "value", backward=lambda v: v == "new")
            continue_button = (
                ui.button("Continue this job", icon="play_arrow")
                .props("no-caps size=lg")
                .mark("continue-button")
            )
            continue_button.bind_visibility_from(job, "value", backward=lambda v: v == "resume")
        check_box = ui.column().classes("w-full gap-2")
        progress_box = ui.column().classes("w-full gap-2")
        result_box = ui.column().classes("w-full gap-2")

    def collect() -> ProcessForm:
        return ProcessForm(
            folder=folder.value,
            out_dir=out.value,
            preset=preset.value,
            recursive=bool(recursive.value),
            photo_size=str(size.value),
            force=bool(force.value),
            keep_repeats=bool(repeats.value),
            profile=str(mapped.value or "forest"),
            engine_url=engine_url.value or "",
            engine_token=engine_token.value or "",
            trees=replace(trees_part.inputs(), off=switch_part.off()),
            clip_file=clip_part.values()[0],
            clip_buffer_m=clip_part.values()[1],
        )

    async def check() -> None:
        check_box.clear()
        form = collect()
        try:
            build_request(form)
        except ProcessFormError as exc:
            _problem(check_box, str(exc))
            return
        with check_box:
            ui.spinner(size="lg")
            ui.label("Checking this computer and your photos...")
        outcome = await run_job(check_computer, form)
        check_box.clear()
        if not outcome.ok or outcome.value is None:
            _problem(check_box, outcome.error or "The check did not finish.")
            return
        show_feasibility(check_box, outcome.value)

    async def start() -> None:
        check_box.clear()
        progress_box.clear()
        result_box.clear()
        form = collect()
        try:
            build_request(form)
        except ProcessFormError as exc:
            _problem(result_box, str(exc))
            return
        STATE.photo_folder = form.folder
        out_dir = Path(form.out_dir.strip() or default_output(form.folder)).expanduser()
        await go(out_dir, execute_process, form)

    async def resume() -> None:
        check_box.clear()
        progress_box.clear()
        result_box.clear()
        try:
            out_dir = resume_part.check()
        except ProcessFormError as exc:
            _problem(result_box, str(exc))
            return
        token = engine_token.value or ""
        await go(out_dir, execute_resume, str(out_dir), token, bool(force.value))

    async def go(out_dir: Path, job_function: Any, *args: Any) -> None:
        cancel.clear()
        reporter = QueueReporter()
        panel = ProgressPanel(progress_box)
        with progress_box:
            timer = ui.timer(0.3, lambda: panel.apply(reporter.drain()))
        for button in (start_button, check_button, continue_button):
            button.disable()
        cancel_button.set_visibility(True)
        outcome = await run_job(job_function, *args, reporter, cancel)
        timer.cancel()
        panel.apply(reporter.drain())
        cancel_button.set_visibility(False)
        for button in (start_button, check_button, continue_button):
            button.enable()
        done = outcome.ok and outcome.value is not None and outcome.value.outcome is not None
        completed = done and outcome.value.outcome.completed  # type: ignore[union-attr]
        panel.finish(ok=bool(completed))
        if not outcome.ok or outcome.value is None:
            _problem(result_box, outcome.error or "The job did not finish.")
            resume_later(result_box, out_dir)
            return
        if completed or work_file(out_dir).is_file():
            STATE.maps_folder = str(out_dir)  # a stopped job too: the project knows where it is
        show_result(result_box, outcome.value, out_dir)
        if not completed:
            resume_later(result_box, out_dir)

    def stop() -> None:
        cancel.set()
        ui.notify(
            "Stopping... if photos are still being sent, this happens when sending is done.",
            type="info",
        )

    check_button.on_click(check)
    start_button.on_click(start)
    continue_button.on_click(resume)
    cancel_button.on_click(stop)
