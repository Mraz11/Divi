# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plan a flight: describe the area and what you want, get missions for DJI Fly."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.adapters.profiles import load_profiles
from avispria.app.ui.drafts import forget, keep, recall, remember
from avispria.app.ui.jobs import run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.pages.plan_form import PlanFormUi
from avispria.app.ui.pages.plan_results import show_plan
from avispria.app.ui.pages.scan_results import show_scan
from avispria.app.ui.plan_job import execute_plan
from avispria.app.ui.scan_job import execute_scan
from avispria.app.ui.state import STATE


async def plan_page() -> None:
    with frame("Plan a flight"):
        ui.label(
            "Answer the five steps from the top. Dīvi then makes missions for DJI Fly and "
            "tells you what you will really get."
        ).classes("text-base")
        form_ui = PlanFormUi(load_profiles())
        keep("plan", form_ui)
        with ui.row().classes("items-center gap-2"):
            button = (
                ui.button("Plan the flight", icon="flight").props("no-caps size=lg").mark("run")
            )
            ui.button(
                "Start a new plan", icon="restart_alt", on_click=lambda: _start_afresh()
            ).props("no-caps flat").mark("plan-afresh")
        results = ui.column().classes("w-full gap-2")
        shown_before = recall("plan", "result")
        if shown_before is not None:  # came back from another step: the plan is still here
            _show(results, *shown_before)

    async def run() -> None:
        results.clear()
        form = form_ui.collect()
        button.disable()
        with results:
            ui.spinner(size="lg")
            ui.label("Planning the flight (hilly sites take a little longer)...")
        is_object = form.scan_type == "object_3d"
        outcome = await run_job(execute_scan if is_object else execute_plan, form)
        button.enable()
        results.clear()
        if not outcome.ok or outcome.value is None:
            with results:
                ui.label(outcome.error or "The plan did not finish.").classes(
                    "av-problem-text font-medium"
                )
            return
        STATE.last_output = form.out_dir
        if outcome.value.outputs is not None:
            STATE.last_plan_files = [str(p) for p in outcome.value.outputs.kmz_paths]
            STATE.last_sent_files = []  # a new plan has not been sent yet
            if Path(form.template).is_file():
                STATE.sample_mission = form.template  # the sample that worked is remembered
        shown = Path(form.out_dir).expanduser()
        remember("plan", "result", (outcome.value, shown, is_object))
        _show(results, outcome.value, shown, is_object)

    button.on_click(run)


def _show(box: ui.column, value: object, out_dir: Path, is_object: bool) -> None:
    if is_object:
        show_scan(box, value, out_dir)  # type: ignore[arg-type]
    else:
        show_plan(box, value, out_dir)  # type: ignore[arg-type]


def _start_afresh() -> None:
    forget("plan")
    ui.navigate.reload()
