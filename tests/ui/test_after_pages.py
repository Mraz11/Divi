# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Steps 5 to 8 on their own: cut, measure, export and report on maps that already exist."""

from pathlib import Path

import pytest
import rasterio
from nicegui.testing import User
from typer.testing import CliRunner

from avispria.app.cli import app
from avispria.app.engines import RECORD_FILE
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.project import load_project
from avispria.app.ui import projects
from avispria.app.ui.after_job import (
    AfterError,
    maps_folder,
    read_provenance,
    run_cut,
    run_measure,
    save_record,
    undo_cut,
)
from avispria.app.ui.state import STATE
from forestscene import N, area_file, scene
from uihelpers import set_text

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]
runner = CliRunner()


@pytest.fixture
def maps(tmp_path: Path) -> Path:
    results, _ = scene(tmp_path)
    return results.parent


def _width(maps: Path) -> int:
    with rasterio.open(maps / "results" / "odm_dem" / "dsm.tif") as src:
        return int(src.width)


def test_the_maps_folder_is_checked_before_anything_runs(tmp_path: Path, maps: Path) -> None:
    assert maps_folder(str(maps)) == maps
    assert maps_folder(str(maps / "results")) == maps  # the results folder itself: one level up
    for text, message in (("  ", "Choose the folder"), (str(tmp_path / "x"), "no maps in")):
        with pytest.raises(AfterError, match=message):
            maps_folder(text)
    assert read_provenance(tmp_path) == {}
    (maps / "divi_provenance.json").write_text('["not a record"]', encoding="utf-8")
    assert read_provenance(maps) == {}


def test_cutting_on_its_own_and_undoing_it(tmp_path: Path, maps: Path) -> None:
    area = area_file(tmp_path, (40, 160), (20, 120), "kml")
    made = projects.start_project("Cut", tmp_path / "projects")
    STATE.maps_folder = str(maps)
    cut = run_cut(str(maps), str(area), 0.0)
    assert len(cut.cut) == 3 and _width(maps) < N
    assert projects.state_of("map").done
    assert load_project(made.folder).engines["map"]["note"] == "cut by area.kml"
    assert len(undo_cut(str(maps))) == 3 and _width(maps) == N
    for call, message in (
        (lambda: undo_cut(str(maps)), "nothing to undo"),
        (lambda: run_cut(str(maps), "", 0.0), "Choose the file with the area"),
        (lambda: run_cut(str(maps), str(tmp_path / "no.kml"), 0.0), "was not found"),
    ):
        with pytest.raises(AfterError, match=message):
            call()
    far = area_file(tmp_path, (4000, 4100), (4000, 4100), "geojson")
    with pytest.raises(AfterError, match="The maps were not cut"):
        run_cut(str(maps), str(far), 0.0)


def test_measuring_on_its_own(tmp_path: Path, maps: Path) -> None:
    STATE.maps_folder = str(maps)
    canopy = run_measure(str(maps), "forest", TreeInputs())
    assert canopy["canopy"]["height_max_m"] > 20
    assert (maps / "results" / "analysis" / "surface_summary.json").is_file()
    assert projects.state_of("analyse").done
    with pytest.raises(AfterError, match="Choose what you mapped"):
        run_measure(str(maps), "ocean", TreeInputs())
    with pytest.raises(AfterError, match="was not found"):
        run_measure(str(maps), "forest", TreeInputs(ground_file=tmp_path / "none.tif"))
    (maps / "results" / "odm_dem" / "dsm.tif").write_bytes(b"not a raster")
    with pytest.raises(AfterError, match="could not be measured"):
        run_measure(str(maps), "forest", TreeInputs())
    (maps / "results" / "odm_dem" / "dsm.tif").unlink()
    with pytest.raises(AfterError, match="no surface model"):
        run_measure(str(maps), "forest", TreeInputs())


def test_making_the_report_finishes_the_report_engine(tmp_path: Path, maps: Path) -> None:
    with pytest.raises(AfterError, match="Make maps first"):
        save_record()
    made = projects.start_project("Recorded", tmp_path / "projects")
    STATE.maps_folder = str(maps)
    path = save_record()
    text = path.read_text(encoding="utf-8")
    assert path == maps / RECORD_FILE and "<h1>Recorded</h1>" in text
    assert "Maps made" in text and "Nothing has been measured yet" in text
    assert "report" in load_project(made.folder).engines and projects.state_of("report").done


async def test_the_cut_screen_cuts_and_undoes(user: User, tmp_path: Path, maps: Path) -> None:
    area = area_file(tmp_path, (40, 160), (20, 120), "geojson")
    STATE.maps_folder = str(maps)
    await user.open("/map")
    await user.should_see("Step 5 of 8")
    await user.should_see("Maps folder")
    user.find(marker="cut-button").click()
    await user.should_see("Choose the file with the area")
    set_text(user, "clip-input", str(area))
    user.find(marker="cut-button").click()
    await user.should_see("Cut (", retries=200)
    await user.should_see("Measure again")
    assert _width(maps) < N
    user.find(marker="uncut-button").click()
    await user.should_see("The uncut maps are back", retries=200)
    user.find(marker="uncut-button").click()
    await user.should_see("nothing to undo", retries=200)


async def test_the_measure_screen_measures_and_shows_what_is_there(user: User, maps: Path) -> None:
    await user.open("/analyse")
    await user.should_see("Step 6 of 8")
    user.find(marker="measure-button").click()
    await user.should_see("Choose the folder where your maps were saved.")
    set_text(user, "measure-folder-input", str(maps))
    user.find(marker="measure-button").click()
    await user.should_see("Your forest", retries=300)
    await user.should_see("Trees and canopy")
    STATE.maps_folder = str(maps)
    await user.open("/analyse")  # measured earlier: shown without measuring again
    await user.should_see("Your forest")


async def test_the_report_screen_shows_every_engine_and_makes_the_report(
    user: User, tmp_path: Path, maps: Path
) -> None:
    await user.open("/report")
    await user.should_see("Unnamed project")
    await user.should_see("How to cite")
    await user.should_see("github.com/Mraz11/Divi")
    user.find(marker="engine-table")
    user.find(marker="save-record").click()
    await user.should_see("Make maps first")
    projects.start_project("Garden", tmp_path / "projects")
    STATE.maps_folder = str(maps)
    await user.open("/report")
    await user.should_see("Project: Garden")
    user.find(marker="save-record").click()
    await user.should_see("Made:", retries=200)
    user.find(marker="open-report")
    assert (maps / RECORD_FILE).is_file()
    await user.open("/report")
    await user.should_see("Made earlier:")


def test_the_project_commands(tmp_path: Path, maps: Path) -> None:
    shown = runner.invoke(app, ["pipeline"])
    assert shown.exit_code == 0 and "5. Map [optional]" in shown.output
    assert "needs: reconstruct" in shown.output
    cited = runner.invoke(app, ["cite"])
    assert cited.exit_code == 0 and "please cite it" in cited.output
    on_maps = runner.invoke(app, ["status", str(maps)])
    assert on_maps.exit_code == 0 and "4. Reconstruct" in on_maps.output
    assert "Maps not cut (optional)" in on_maps.output
    made = projects.start_project("Cmd", tmp_path / "projects")
    STATE.maps_folder = str(maps)
    on_project = runner.invoke(app, ["status", str(made.folder)])
    assert on_project.exit_code == 0 and "Project: Cmd" in on_project.output
    saved = runner.invoke(app, ["report", str(made.folder)])
    assert saved.exit_code == 0 and (maps / RECORD_FILE).is_file()
    assert runner.invoke(app, ["status", str(tmp_path / "nothing")]).exit_code == 2
    empty = projects.start_project("Empty", tmp_path / "projects")
    assert runner.invoke(app, ["report", str(empty.folder)]).exit_code == 2
    (empty.folder / "divi_project.json").write_text("{broken", encoding="utf-8")
    assert runner.invoke(app, ["status", str(empty.folder)]).exit_code == 2


async def test_switches_on_the_measure_screen_are_used_and_remembered(
    user: User, maps: Path
) -> None:
    STATE.maps_folder = str(maps)
    await user.open("/analyse")
    await user.should_see("What to measure")
    await user.should_see("Always done: the canopy height model")
    user.find(marker="switch-landcover").click()
    user.find(marker="switch-biomass").click()
    assert STATE.analyses_off == ["landcover", "biomass"]
    user.find(marker="measure-button").click()
    await user.should_see("Trees and canopy", retries=300)
    assert not (maps / "results" / "analysis" / "landcover.tif").exists()
    await user.open("/process")
    await user.should_see("What to measure")  # the same switches, remembered
    assert next(iter(user.find(marker="switch-landcover").elements)).value is False


async def test_the_export_screen_exports_and_offers_xylo_forest_later(
    user: User, maps: Path
) -> None:
    await user.open("/export")
    await user.should_see("Step 7 of 8")
    await user.should_see("Prepare for Xylo Forest")
    assert next(iter(user.find(marker="export-xylo").elements)).props.get("disable") is not None
    user.find(marker="export-button").click()
    await user.should_see("Choose the folder where your maps were saved.", retries=100)
    STATE.maps_folder = str(maps)
    await user.open("/export")
    user.find(marker="export-vectors").click()  # nothing measured: no layers to export anyway
    user.find(marker="export-button").click()
    await user.should_see("bands/red.tif", retries=300)
    await user.should_see("Not exported:")
    user.find(marker="export-open")
    assert projects.state_of("export").done


async def test_the_map_image_screen_previews_and_saves(user: User, maps: Path) -> None:
    await user.open("/figure")
    await user.should_see("Step 7 of 8")
    await user.should_see("Press Preview")
    user.find(marker="figure-preview-button").click()
    await user.should_see("Choose the folder where your maps were saved.", retries=100)
    set_text(user, "figure-folder-input", str(maps))
    await user.should_see("170 mm wide, height fits the map; 300 dpi = 2008 pixels wide")
    user.find(marker="figure-preview-button").click()
    await user.should_see("This is the layout that will be saved", retries=300)
    image = next(iter(user.find(marker="figure-image").elements))
    assert str(image.source).startswith("data:image/png;base64,")
    user.find(marker="figure-save").click()
    await user.should_see("Saved:", retries=300)
    assert list((maps / "export" / "figures").glob("*.png"))
