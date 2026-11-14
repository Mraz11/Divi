# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The optional tree inventory inputs on Make maps, and the inventory on the results."""

from dataclasses import replace
from pathlib import Path

import pytest
from nicegui.testing import User

from avispria.app.inventory_workflow import TreeInputs
from avispria.app.ui.pages.canopy_section import inventory_tiles
from avispria.app.ui.process_job import ProcessForm, ProcessFormError, build_request
from photobuild import make_dji_jpeg
from uihelpers import set_text

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


def form(tmp_path: Path) -> ProcessForm:
    folder = tmp_path / "flight"
    folder.mkdir()
    make_dji_jpeg(folder / "DJI_0001.JPG", size=(800, 600), lat=22.282, lon=91.779)
    return ProcessForm(folder=str(folder), out_dir=str(tmp_path / "out"))


def test_tree_inputs_reach_the_job_and_missing_files_are_named(tmp_path: Path) -> None:
    base = form(tmp_path)
    csv_file = tmp_path / "trees.csv"
    csv_file.write_text("lat,lon,height_m\n", encoding="utf-8")
    trees = TreeInputs(field_heights=csv_file)
    assert build_request(replace(base, trees=trees)).trees == trees
    with pytest.raises(ProcessFormError, match="ground model from elsewhere was not found"):
        build_request(replace(base, trees=TreeInputs(ground_file=tmp_path / "no.tif")))
    same = tmp_path / "g.tif"
    same.write_bytes(b"x")
    with pytest.raises(ProcessFormError, match="other than the one used"):
        build_request(replace(base, trees=TreeInputs(ground_file=same, reference_file=same)))


def test_the_inventory_tiles() -> None:
    summary = {
        "quality": {"grade": "use with care", "findings": ["a"], "doming": {"domed": True}},
        "ground_choice": {"kind": "lidar"},
        "height_calibration": {"method": "line", "note": "9 field trees"},
        "biomass": {
            "trees": 9,
            "agb_kg_jucker": {"median": 5000, "low": 3000, "high": 9000},
            "co2e_kg": {"median": 8600, "low": 5000, "high": 15000},
            "one_tree_band": 4.1,
        },
        "symptoms": {"candidates": 2, "candidate_crown_area_pct": 12.5},
    }
    tiles = {t.label: t for t in inventory_tiles(summary)}
    assert tiles["Height model"].value == "use with care"
    assert tiles["Doming"].value == "found"
    assert tiles["Biomass above ground"].value == "5.0 t"
    assert "4.1x" in tiles["CO2 equivalent"].hint
    assert tiles["Visible symptoms"].value == "2 crowns"


async def test_the_tree_inputs_are_on_the_screen(user: User, tmp_path: Path) -> None:
    await user.open("/process")
    await user.should_see("Trees: heights, biomass and carbon (optional inputs)")
    set_text(user, "trees-field-input", str(tmp_path / "missing.csv"))
    set_text(user, "photos-input", str(form(tmp_path).folder))
    user.find(marker="start-button").click()
    await user.should_see("was not found")


def test_the_area_to_cut_by_is_checked(tmp_path: Path) -> None:
    base = form(tmp_path)
    kml = tmp_path / "a.kml"
    kml.write_text("<kml/>", encoding="utf-8")
    request = build_request(replace(base, clip_file=str(kml), clip_buffer_m=5))
    assert request.clip_file == kml and request.clip_buffer_m == 5
    assert build_request(base).clip_file is None
    with pytest.raises(ProcessFormError, match="was not found"):
        build_request(replace(base, clip_file=str(tmp_path / "no.kml")))
    txt = tmp_path / "a.txt"
    txt.write_text("x", encoding="utf-8")
    with pytest.raises(ProcessFormError, match="Cut by a"):
        build_request(replace(base, clip_file=str(txt)))


async def test_the_cut_inputs_are_on_the_screen(user: User) -> None:
    await user.open("/process")
    await user.should_see("Cut the maps to your area (optional)")
