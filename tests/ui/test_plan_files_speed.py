# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plan from a map file (with a buffer), the object map's full screen, and the speed settings."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from nicegui.testing import User

from avispria.app.ui.plan_job import FormError, PlanForm, build_inputs, execute_plan
from avispria.core.shapes import Role
from uihelpers import set_text

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]

LON, LAT = 90.4120, 23.8100  # the same fictional test place as the other plan tests
D = 0.0008
SQUARE = [[LON, LAT], [LON + D, LAT], [LON + D, LAT + D], [LON, LAT + D], [LON, LAT]]
HOLE = [[LON + 3e-4, LAT + 3e-4], [LON + 4e-4, LAT + 3e-4], [LON + 4e-4, LAT + 4e-4],
        [LON + 3e-4, LAT + 3e-4]]  # fmt: skip
KML = (
    '<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Polygon><outerBoundaryIs>'
    "<LinearRing><coordinates>{}</coordinates></LinearRing></outerBoundaryIs></Polygon>"
    "</Placemark></kml>"
)


def kml(path: Path, ring: list[list[float]]) -> Path:
    path.write_text(KML.format(" ".join(f"{x},{y}" for x, y in ring)), encoding="utf-8")
    return path


def test_a_kml_area_is_planned_and_a_buffer_makes_it_bigger(
    tmp_path: Path, plan_form: PlanForm
) -> None:
    form = replace(plan_form, area_mode="file", aoi_file=str(kml(tmp_path / "a.kml", SQUARE)))
    exact = build_inputs(form)
    wide = build_inputs(replace(form, aoi_buffer_m=30.0, out_dir=str(tmp_path / "wide")))
    small = json.loads(exact.aoi_path.read_text("utf-8"))["coordinates"][0]
    big = json.loads(wide.aoi_path.read_text("utf-8"))["coordinates"][0]
    assert max(p[0] for p in big) > max(p[0] for p in small) + 2e-4
    assert execute_plan(form, now_ms=0).outputs is not None


def test_a_file_with_two_separate_areas_asks_to_choose(tmp_path: Path, plan_form: PlanForm) -> None:
    doc = {"type": "MultiPolygon", "coordinates": [[SQUARE], [[[x + 0.01, y] for x, y in SQUARE]]]}
    (tmp_path / "two.geojson").write_text(json.dumps(doc), encoding="utf-8")
    form = replace(plan_form, area_mode="file", aoi_file=str(tmp_path / "two.geojson"))
    with pytest.raises(FormError, match="2 separate areas"):
        build_inputs(form)
    # a buffer wide enough joins them into one area
    assert build_inputs(replace(form, aoi_buffer_m=600.0)).aoi_path.exists()


def test_a_chosen_speed_limit_and_photo_interval_reach_the_plan(plan_form: PlanForm) -> None:
    inputs = build_inputs(replace(plan_form, speed_limit_ms=4.0, photo_interval_s=1.0))
    assert inputs.options.speed_limit_ms == 4.0 and inputs.options.photo_interval_s == 1.0
    result = execute_plan(replace(plan_form, speed_limit_ms=4.0), now_ms=0)
    assert result.outputs is not None
    assert result.outputs.result.summary.speed.speed_ms <= 4.0
    with pytest.raises(FormError, match="at most 12"):
        build_inputs(replace(plan_form, speed_limit_ms=15.0))
    with pytest.raises(FormError, match="at least 1"):
        build_inputs(replace(plan_form, speed_limit_ms=0.5))
    with pytest.raises(FormError, match=r"0\.3 seconds"):
        build_inputs(replace(plan_form, photo_interval_s=0.1))


async def test_the_file_is_read_at_once_and_shown_on_the_map(
    user: User, maps: list, tmp_path: Path
) -> None:  # type: ignore[type-arg]
    with_hole = tmp_path / "hole.geojson"
    with_hole.write_text(json.dumps({"type": "Polygon", "coordinates": [SQUARE, HOLE]}))
    await user.open("/plan")
    next(iter(user.find(marker="area-mode").elements)).set_value("file")
    set_text(user, "aoi-input", str(tmp_path / "missing.kml"))
    await user.should_see("This file cannot be used")
    set_text(user, "aoi-input", str(with_hole))
    await user.should_see("Area to map:")
    kind = next(iter(user.find(marker="aoi-buffer-kind").elements))
    kind.set_value("buffer")  # a 20 m buffer fills the small hole...
    await user.should_see("Area to map:")
    kind.set_value("exact")  # ...exactly the shape keeps it as a part to leave out
    user.find(marker="aoi-to-map").click()
    await user.should_see("Show map background", retries=100)
    area = maps[0]
    assert [s.role for s in area.shapes] == [Role.INSIDE, Role.LEAVE_OUT]


async def test_an_empty_file_choice_cannot_go_to_the_map(user: User) -> None:
    await user.open("/plan")
    next(iter(user.find(marker="area-mode").elements)).set_value("file")
    user.find(marker="aoi-to-map").click()
    await user.should_see("Choose a map file")


async def test_the_object_map_has_full_screen(user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    from avispria.app.ui.pages import plan_object, plan_pin_map

    created: list = []  # type: ignore[type-arg]

    class Recording(plan_pin_map.PinMap):
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(plan_object, "PinMap", Recording)
    await user.open("/plan")
    next(iter(user.find(marker="scan-type").elements)).set_value("object_3d")
    user.find(marker="object-open-map").click()
    await user.should_see("Right-drag to move the map")
    pin = created[0]
    user.find(marker="map-full").click()
    assert pin.full and "av-full" in pin.box.classes
    await user.should_see("Exit full screen")
    escape = SimpleNamespace(key=SimpleNamespace(escape=True), action=SimpleNamespace(keydown=True))
    pin._key(escape)
    assert not pin.full and "av-full" not in pin.box.classes


def test_a_drone_without_dji_fly_missions_is_refused_kindly(
    plan_form: PlanForm, tmp_path: Path
) -> None:
    from avispria.adapters.profiles import load_profiles

    extra = tmp_path / "other.toml"
    extra.write_text(
        '[other]\nname = "DJI Other"\nmax_speed_ms = 20\ndrone_enum = 0\nwaypoint_limit = 99\n'
        'mission_app = "waypoint-pro"\n[other.modes.12mp]\nsensor_width_mm = 9.7\n'
        "sensor_height_mm = 7.3\nfocal_mm = 6.72\nimage_width_px = 4032\nimage_height_px = 3024\n"
        "min_interval_s = 2\nreadout_s = 0.03\n",
        encoding="utf-8",
    )
    profiles = load_profiles(extra)
    with pytest.raises(FormError, match="Waypoint Pro"):
        build_inputs(replace(plan_form, aircraft="other"), profiles)


async def test_the_goal_helper_fills_the_settings(user: User) -> None:
    await user.open("/plan")
    goal = next(iter(user.find(marker="goal-select").elements))
    goal.set_value("plants")
    set_text(user, "goal-size", "0.05")
    user.find(marker="goal-suggest").click()
    await user.should_see("cm per pixel")
    target = next(iter(user.find(marker="target-input").elements))
    assert target.value == pytest.approx(1.0)
    goal.set_value("lesions")
    user.find(marker="goal-suggest").click()
    await user.should_see("Not reachable from a mapping flight")
    assert target.value == pytest.approx(1.0)  # left as it was
