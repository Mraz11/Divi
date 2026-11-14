# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Continue a stopped processing job from the Make maps screen."""

import threading
from pathlib import Path

import pytest
from nicegui.testing import User

from avispria.app.process_work import load_work
from avispria.app.process_workflow import ProcessRequest, run_process
from fakes.nodeodx import fake_engine
from photobuild import make_dji_jpeg
from uihelpers import set_text

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]
LONG = 200


class Quiet:
    def __init__(self, stop: threading.Event) -> None:
        self.stop = stop

    def step(self, title: str) -> None: ...
    def info(self, text: str) -> None: ...
    def warn(self, text: str) -> None: ...
    def upload(self, percent: float) -> None: ...

    def progress(self, percent: float, status: str) -> None:
        self.stop.set()


def photos(tmp_path: Path) -> Path:
    folder = tmp_path / "flight"
    folder.mkdir()
    for i in range(6):
        make_dji_jpeg(
            folder / f"DJI_{i:04d}.JPG",
            size=(800, 600),
            lat=22.2820 + (i % 3) * 0.0001,
            lon=91.7790 + (i // 3) * 0.0002,
        )
    return folder


async def test_a_stopped_job_is_continued_from_its_results_folder(
    user: User, machine, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "out"
    with fake_engine(None, outcome="hang") as (port, state):
        machine(port=port)
        stop = threading.Event()
        request = ProcessRequest(folder=photos(tmp_path), out_dir=out, resize_mp=None, cancel=stop)
        assert not run_process(request, Quiet(stop)).completed
        await user.open("/process")
        next(iter(user.find(marker="job-kind").elements)).set_value("resume")
        set_text(user, "resume-input", str(tmp_path))
        await user.should_see("There is no Dīvi work record")
        set_text(user, "resume-input", str(out))
        await user.should_see("the photos were sent to the engine")
        user.find(marker="continue-button").click()
        await user.should_see("Your results", retries=LONG)
        assert state.restarts == 1 and state.uploads == 6
    assert load_work(out).step == "done"


async def test_continue_needs_a_folder_with_a_record(user: User, tmp_path: Path) -> None:
    await user.open("/process")
    next(iter(user.find(marker="job-kind").elements)).set_value("resume")
    set_text(user, "resume-input", "")
    user.find(marker="continue-button").click()
    await user.should_see("Choose the results folder")
    set_text(user, "resume-input", str(tmp_path / "nowhere"))
    user.find(marker="continue-button").click()
    await user.should_see("does not exist")


async def test_maps_only_opens_on_making_maps_without_the_flight_screens(user: User) -> None:
    from avispria.app.ui import layout

    layout.MAPS_ONLY["on"] = True
    try:
        await user.open("/process")
        await user.should_see("Maps: after the flight")
        await user.should_see("Continue a job that stopped")
        await user.should_not_see("1. Plan a flight")
    finally:
        layout.MAPS_ONLY["on"] = False
