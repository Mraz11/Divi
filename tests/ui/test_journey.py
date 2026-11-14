# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
from types import SimpleNamespace

import pytest
from nicegui.testing import User

from avispria.app.ui.journey import STEPS, nav_items, nav_label, neighbours, screens, step_for
from avispria.app.ui.state import STATE
from avispria.core.pipeline import ENGINES, TOTAL
from uihelpers import eventually

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]

ORDER = [
    "/plan",
    "/phone",
    "/fly",
    "/check",
    "/process",
    "/map",
    "/analyse",
    "/export",
    "/figure",
    "/report",
]
ENGINE_NAV = [
    "1 Plan",
    "2 Mission",
    "3 Photo check",
    "4 Reconstruct",
    "5 Map",
    "6 Analyse",
    "7 Export",
    "8 Report",
]


def test_the_journey_is_the_pipeline_in_the_order_a_project_goes() -> None:
    assert [s.path for s in STEPS] == ORDER
    assert [s.number for s in STEPS] == [1, 2, 2, 3, 4, 5, 6, 7, 7, 8]  # Mission, Export: two
    assert TOTAL == 8 == len(ENGINES)
    assert [s.engine for s in STEPS] == [
        "plan",
        "mission",
        "mission",
        "photos",
        "reconstruct",
        "map",
        "analyse",
        "export",
        "export",
        "report",
    ]
    assert nav_items()[0] == ("Start", "/", "")
    assert [label for label, _, _ in nav_items()[1:]] == ENGINE_NAV
    assert [path for _, path, _ in nav_items()[1:]] == [
        "/plan",
        "/phone",
        "/check",
        "/process",
        "/map",
        "/analyse",
        "/export",
        "/report",
    ]
    assert [label for label, _, _ in nav_items(maps_only=True)] == ENGINE_NAV[3:]
    assert [s.path for s in screens(maps_only=True)] == ORDER[4:]
    assert (
        step_for("Fly") is STEPS[2] and step_for("Start") is None and step_for("nonsense") is None
    )
    assert all(s.what.strip().endswith(".") for s in STEPS)
    assert neighbours(STEPS[0]) == (None, STEPS[1]) and neighbours(STEPS[-1]) == (STEPS[-2], None)
    assert neighbours(STEPS[4], maps_only=True) == (None, STEPS[5])


@pytest.mark.parametrize("path", ORDER)
async def test_every_screen_says_which_step_it_is_and_links_back_and_forward(
    user: User, path: str
) -> None:
    at = ORDER.index(path)
    step = STEPS[at]
    await user.open(path)
    await user.should_see(f"Step {step.number} of 8")
    await user.should_see(step.what)
    user.find(marker="journey-bar")
    user.find(marker="step-status")
    if at > 0:
        await user.should_see(f"Back: {nav_label(STEPS[at - 1])}")
        user.find(marker="back-button")
        user.find(marker="back-step-button")
    else:
        with pytest.raises(AssertionError):
            user.find(marker="back-button")
    if at + 1 < len(STEPS):
        await user.should_see(f"Next: {nav_label(STEPS[at + 1])}")
        await user.should_see("When you are done here")
        user.find(marker="forward-button")
        user.find(marker="next-step-button")
    else:
        await user.should_see("That is the whole journey")
        await user.should_see("Start a new project")


@pytest.mark.parametrize("index", range(9))
async def test_next_goes_to_the_next_screen_and_back_returns(user: User, index: int) -> None:
    await user.open(ORDER[index])
    user.find(marker="next-step-button").click()
    await user.should_see(f"Back: {nav_label(STEPS[index])}", retries=100)  # only there
    user.find(marker="back-button").click()
    await user.should_see(f"Next: {nav_label(STEPS[index + 1])}", retries=100)
    await user.should_not_see(f"Back: {nav_label(STEPS[index])}")


async def test_the_last_step_offers_a_new_project(user: User, tmp_path: Path) -> None:
    mission = tmp_path / "divi_01.kmz"
    mission.write_bytes(b"kmz")
    STATE.last_plan_files = [str(mission)]
    STATE.maps_folder = str(tmp_path)
    await user.open("/report")
    user.find(marker="next-step-button").click()
    await user.should_see("Start a new project?", retries=100)
    user.find(marker="new-project-confirm").click()
    await eventually(lambda: STATE.last_plan_files == [] and STATE.maps_folder == "")
    assert mission.is_file()  # nothing is deleted


async def test_the_top_bar_has_every_engine_marks_the_current_one_and_what_is_done(
    user: User, tmp_path: Path
) -> None:
    from nicegui import ui

    mission = tmp_path / "a.kmz"
    mission.write_bytes(b"x")
    STATE.last_plan_files = [str(mission)]
    await user.open("/fly")
    bar = [e for e in user.find(kind=ui.link).elements if "av-nav" in e.classes]
    assert {e.text for e in bar} == {"Start", *ENGINE_NAV}  # their order: the data test above
    assert [e.text for e in bar if "av-nav-active" in e.classes] == ["2 Mission"]
    assert [e.text for e in bar if "av-nav-done" in e.classes] == ["1 Plan"]
    await user.open("/")
    bar = [e for e in user.find(kind=ui.link).elements if "av-nav" in e.classes]
    assert [e.text for e in bar if "av-nav-active" in e.classes] == ["Start"]


async def test_the_start_page_is_the_journey_with_a_place_to_start(user: User) -> None:
    await user.open("/")
    await user.should_see("A project has 8 steps. Do them in this order.")
    await user.should_see(
        "Plan -> Mission -> Photo check -> Reconstruct -> Map -> Analyse -> Export -> Report"
    )
    for step in STEPS:
        await user.should_see(step.title)
        await user.should_see(step.what)
        user.find(marker=f"open-{step.path.strip('/')}")
    await user.should_see("Start here")
    await user.should_see("Go: 1. Plan a flight")
    user.find(marker="open-plan").click()
    await user.should_see("Step 1 of 8", retries=100)


async def test_the_fly_screen_says_what_to_check_and_what_to_do_afterwards(user: User) -> None:
    STATE.last_plan_files = ["a.kmz", "b.kmz", "c.kmz"]
    await user.open("/fly")
    await user.should_see("Your last plan has 3 missions.")
    for text in (
        "Before you leave",
        "If DJI Fly shows different numbers",
        "Global Speed",
        "avispria inspect",
        "At the site",
        "After landing",
        "spot-check sheet",
        "ONE folder",
        "mraz11.github.io/Divi",
    ):
        await user.should_see(text)
    STATE.last_plan_files = ["a.kmz"]
    await user.open("/fly")
    await user.should_see("Your last plan has 1 mission.")
    STATE.last_plan_files = []
    await user.open("/fly")
    await user.should_not_see("Your last plan has")


def remember(
    tmp_path: Path, *, sample: bool = False, planned: int = 0, sent: int = 0, checked: bool = False
) -> None:
    """Put the project in a state, the way the screens leave it."""
    if sample:
        (tmp_path / "sample.kmz").write_bytes(b"x")
        STATE.sample_mission = str(tmp_path / "sample.kmz")
    plans = []
    for n in range(planned):
        f = tmp_path / f"survey_0{n + 1}.kmz"
        f.write_bytes(b"x")
        plans.append(str(f))
    STATE.last_plan_files = plans
    STATE.last_sent_files = plans[:sent]
    if checked:
        (tmp_path / "photos").mkdir()
        STATE.photo_folder = str(tmp_path / "photos")


async def test_a_new_project_starts_with_the_sample_mission_right_on_the_start_page(
    user: User,
) -> None:
    await user.open("/")
    await user.should_see("Your next step")
    await user.should_see("First, once: get your sample mission from the phone")
    user.find(marker="sample-from-phone")  # the action is here, not on another screen
    with pytest.raises(AssertionError):
        user.find(marker="next-action-button")
    await user.should_see("Start here")


async def test_getting_the_sample_on_the_start_page_moves_on_to_planning(
    user: User, fake_phone: SimpleNamespace
) -> None:
    await user.open("/")
    user.find(marker="sample-from-phone").click()
    await user.should_see("Plan your flight", retries=200)
    user.find(marker="next-action-button")
    user.find(marker="next-action-button").click()
    await user.should_see("Step 1 of 8", retries=100)


@pytest.mark.parametrize(
    ("state", "title", "step_done", "step_next"),
    [
        ({"sample": True}, "Plan your flight", [], 1),
        ({"sample": True, "planned": 3}, "Send your 3 missions to DJI Fly", [1], 2),
        ({"sample": True, "planned": 3, "sent": 3}, "Fly, then check your photos", [1, 2], 3),
        (
            {"sample": True, "planned": 3, "sent": 3, "checked": True},
            "Make your map or 3D model",
            [1, 2, 3],
            4,
        ),
    ],
    ids=["planned nothing", "planned", "sent", "checked"],
)
async def test_the_start_page_always_says_the_one_next_thing_and_marks_what_is_done(
    user: User,
    tmp_path: Path,
    state: dict,
    title: str,
    step_done: list,
    step_next: int,  # type: ignore[type-arg]
) -> None:
    remember(tmp_path, **state)
    await user.open("/")
    await user.should_see(title)
    target = {1: "plan", 2: "phone", 3: "fly", 4: "process"}[step_next]
    for step in STEPS:
        name = step.path.strip("/")
        card = next(iter(user.find(marker=f"step-{name}").elements))
        assert ("av-note-info" in card.classes) == (name == target)  # only the next one
    if step_done:
        await user.should_see("Done")
        await user.should_see("Do this next" if step_next != 1 else "Start here")


async def test_the_next_button_goes_to_the_screen_it_names(user: User, tmp_path: Path) -> None:
    remember(tmp_path, sample=True, planned=2)
    await user.open("/")
    await user.should_see("Next: 2. Send to DJI Fly")
    user.find(marker="next-action-button").click()
    await user.should_see("Step 2 of 8", retries=100)
    await user.should_see("Before you send")


async def test_every_screen_shows_where_its_engine_stands(user: User, tmp_path: Path) -> None:
    remember(tmp_path, sample=True, planned=2)
    status = lambda: next(iter(user.find(marker="step-status").elements))  # noqa: E731
    await user.open("/plan")
    assert status().text == "Done" and status().props["icon"] == "check_circle"
    await user.should_see("2 missions planned")
    await user.open("/phone")
    assert status().text == "Ready to do"
    await user.should_see("Nothing sent yet")
    await user.open("/map")
    assert status().text == "Needs an earlier step"


async def test_maps_only_walks_the_four_screens_after_the_flight(user: User) -> None:
    from avispria.app.ui import layout

    layout.MAPS_ONLY["on"] = True
    try:
        await user.open("/process")
        with pytest.raises(AssertionError):
            user.find(marker="back-button")  # nothing before making maps in Dīvi Maps
        await user.should_see("Next: 5. Cut the maps")
        await user.should_not_see("1 Plan")
        await user.should_see("4 Reconstruct")
        await user.open("/report")
        await user.should_see("That is the whole journey")
        await user.should_not_see("Start a new project")
    finally:
        layout.MAPS_ONLY["on"] = False


def test_the_flight_line_is_green_up_to_the_last_finished_step() -> None:
    from avispria.app.ui.layout import last_reached

    keys = ["", "plan", "mission", "photos"]
    assert last_reached(keys, set()) == 0
    assert last_reached(keys, {"plan", "photos"}) == 3  # a gap is still flown over
    assert last_reached(keys, {"nothing"}) == 0


async def test_the_top_bar_marks_where_you_are_and_how_far_the_project_is(
    user: User, tmp_path: Path
) -> None:
    from nicegui import ui

    mission = tmp_path / "a.kmz"
    mission.write_bytes(b"x")
    STATE.last_plan_files = [str(mission)]
    STATE.last_sent_files = [str(mission)]
    await user.open("/check")
    user.find(marker="transect")
    links = {e.text: e for e in user.find(kind=ui.link).elements if "av-nav" in e.classes}
    assert "av-nav-start" in links["Start"].classes
    assert (
        "av-nav-reached" in links["Start"].classes and "av-nav-reached" in links["1 Plan"].classes
    )
    assert "av-nav-tip" in links["2 Mission"].classes  # the line ends at the last finished step
    assert links["3 Photo check"].props.get("aria-current") == "page"
    assert not {"av-nav-reached", "av-nav-tip"} & set(links["4 Reconstruct"].classes)
