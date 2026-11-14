# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""After the first real flight: drafts kept between steps, take-off by a click, the phone's
missions with their times on the first screen."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from nicegui.testing import User

from avispria.app.phone_workflow import Slot
from avispria.app.ui import drafts
from avispria.app.ui.views import slot_label
from uihelpers import eventually, set_text, value_of

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]

BIG = {
    "_latlngs": [
        [
            {"lat": 51.4760, "lng": -0.0030},
            {"lat": 51.4760, "lng": 0.0000},
            {"lat": 51.4778, "lng": 0.0000},
            {"lat": 51.4778, "lng": -0.0030},
        ]
    ]
}


async def test_the_plan_form_and_map_survive_going_to_another_step(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    await user.open("/plan")
    set_text(user, "battery-input", "25")
    next(iter(user.find(marker="area-mode").elements)).set_value("drawn")
    await user.should_see("Show map background", retries=100)
    maps[0].add_drawn("rectangle", BIG)
    await user.open("/check")  # somewhere else
    await user.open("/plan")  # and back
    await user.should_see("Rectangle 1", retries=100)
    assert float(value_of(user, "battery-input")) == 25.0
    area = maps[-1]
    assert len(area.shapes) == 1 and area.geojson()
    user.find(marker="plan-afresh")  # and a way to start over


async def test_a_click_on_the_map_sets_the_takeoff(user: User, maps) -> None:  # type: ignore[no-untyped-def]
    await user.open("/plan")
    next(iter(user.find(marker="area-mode").elements)).set_value("drawn")
    await user.should_see("Click to set take-off", retries=100)
    area = maps[0]
    area._map_click(SimpleNamespace(args={"latlng": {"lat": 51.4755, "lng": -0.0031}}))
    assert area.takeoff is None  # a plain click does nothing
    user.find(marker="map-pick-takeoff").click()
    area._map_click(SimpleNamespace(args={"latlng": {"lat": 51.4755, "lng": -0.0031}}))
    await eventually(lambda: area.takeoff == (-0.0031, 51.4755))
    assert value_of(user, "takeoff-input") == "51.475500, -0.003100"
    area.undo()
    assert area.takeoff is None


async def test_the_phone_missions_are_listed_on_the_plan_screen(
    user: User, fake_phone: SimpleNamespace
) -> None:
    await user.open("/plan")
    user.find(marker="sample-list").click()
    await user.should_see("mission(s) in DJI Fly, newest first", retries=200)
    await user.should_see("made ", retries=50)
    user.find(marker="use-59B88CA7").click()
    await user.should_see("Sample mission:", retries=200)


def test_a_slot_says_when_it_was_made_and_changed() -> None:
    made, changed = datetime(2026, 11, 7, 9, 5), datetime(2026, 11, 7, 17, 40)
    slot = Slot("59B88CA7-CDF1", 12, made, changed, None, None)
    text = slot_label(slot)
    assert "made 07 Nov 2026 09:05" in text and "changed 07 Nov 2026 17:40" in text
    assert "changed" not in slot_label(Slot("A" * 12, 2, made, made, None, None))


def test_drafts_recall_and_forget() -> None:
    drafts.remember("x", "a", 1)
    assert drafts.recall("x", "a") == 1 and drafts.recall("x", "b", 2) == 2
    drafts.forget("x")
    assert drafts.recall("x", "a") is None
    drafts.remember("y", "a", 1)
    drafts.forget()
    assert drafts.DRAFTS == {}
