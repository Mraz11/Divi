# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import pytest

from avispria.app.engines import (
    EXPORT_FILE,
    RECORD_FILE,
    Links,
    finished,
    has_results,
    inspect,
    runner,
)
from avispria.app.process_work import WorkRecord, save_work
from avispria.app.project import (
    MANIFEST,
    Project,
    ProjectError,
    create_project,
    free_folder,
    is_project,
    load_project,
    save_project,
    slug,
    stamp,
    update_links,
)
from avispria.app.report_workflow import ReportError, write_record
from avispria.core.pipeline import KEYS


def _maps(tmp_path: Path) -> Path:
    maps = tmp_path / "maps"
    (maps / "results" / "odm_orthophoto").mkdir(parents=True)
    (maps / "results" / "odm_orthophoto" / "odm_orthophoto.tif").write_bytes(b"tif")
    return maps


def test_a_project_is_a_folder_with_a_record_and_no_coordinates(tmp_path: Path) -> None:
    folder = tmp_path / "sal"
    made = create_project(folder, "  Sal block A ")
    assert is_project(folder) and made.name == "Sal block A" and made.created
    raw = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    assert set(raw) == {
        "name",
        "created",
        "plan_files",
        "sent_files",
        "photo_folder",
        "maps_folder",
        "engines",
        "version",
        "format",
    }
    assert load_project(folder) == made
    for bad, message in (("", "Give the project a name"), ("again", "already a project")):
        with pytest.raises(ProjectError, match=message):
            create_project(folder, bad)
    file = tmp_path / "f.txt"
    file.write_text("x")
    with pytest.raises(ProjectError, match="a file, not a folder"):
        create_project(file, "x")


def test_paths_inside_the_project_move_with_it(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    create_project(folder, "P")
    inside, outside = folder / "missions" / "a.kmz", tmp_path / "elsewhere" / "photos"
    update_links(folder, {"plan_files": [str(inside)], "photo_folder": str(outside)})
    raw = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    assert raw["plan_files"] == ["missions/a.kmz"] and raw["photo_folder"] == str(outside)
    moved = tmp_path / "moved"
    folder.rename(moved)
    found = load_project(moved)
    assert found.plan_files == [str(moved / "missions" / "a.kmz")]
    assert found.photo_folder == str(outside)


def test_changed_links_stamp_their_engine_and_emptied_ones_lose_it(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    create_project(folder, "P")
    plan = [str(tmp_path / "a.kmz")]
    found = update_links(folder, {"plan_files": plan, "maps_folder": str(tmp_path)})
    assert set(found.engines) == {"plan", "reconstruct"}
    assert found.engines["plan"]["version"] and found.engines["plan"]["finished"]
    found = update_links(folder, {"plan_files": [], "maps_folder": str(tmp_path)})
    assert set(found.engines) == {"reconstruct"}
    stamp(found, "map", "cut by area.kml")
    assert found.engines["map"]["note"] == "cut by area.kml"
    with pytest.raises(ProjectError, match="no engine"):
        stamp(found, "fly")


def test_a_record_that_cannot_be_used_says_why(tmp_path: Path) -> None:
    with pytest.raises(ProjectError, match="There is no Dīvi project"):
        load_project(tmp_path)
    (tmp_path / MANIFEST).write_text("{not json", encoding="utf-8")
    with pytest.raises(ProjectError, match="could not be read"):
        load_project(tmp_path)
    (tmp_path / MANIFEST).write_text('["a list"]', encoding="utf-8")
    with pytest.raises(ProjectError, match="not a Dīvi project record"):
        load_project(tmp_path)
    (tmp_path / MANIFEST).write_text(
        '{"name": "N", "engines": {"plan": {"finished": 1}, "nonsense": {}}, "plan_files": 3}',
        encoding="utf-8",
    )
    found = load_project(tmp_path)
    assert found.engines == {"plan": {"finished": "1"}} and found.plan_files == []
    blocked = tmp_path / "file"
    blocked.write_text("x")
    with pytest.raises(ProjectError, match="could not be written"):
        save_project(Project(blocked / "under-a-file", "N"))


def test_folder_names_are_safe_and_never_reused(tmp_path: Path) -> None:
    assert slug("Sal forest / block: A. ") == "Sal-forest-block-A" and slug(" .. ") == "project"
    assert slug("শালবন ১") == "শালবন-১"  # any script, not only Latin
    first = free_folder(tmp_path, "Sal")
    first.mkdir()
    assert first.name == "Sal" and free_folder(tmp_path, "Sal").name == "Sal-2"


def test_every_engine_says_where_it_stands_from_what_is_on_disk(tmp_path: Path) -> None:
    empty = {s.spec.key: s for s in inspect(Links())}
    assert [s.status for s in empty.values()] == [
        "ready",
        "waiting",
        "ready",
        "waiting",
        "waiting",
        "waiting",
        "waiting",
        "waiting",
    ]
    assert empty["plan"].detail == "No plan yet" and empty["map"].label == "Needs an earlier step"
    mission, photos, maps = tmp_path / "a.kmz", tmp_path / "photos", _maps(tmp_path)
    mission.write_bytes(b"x")
    photos.mkdir()
    links = Links((str(mission), "gone.kmz"), (str(mission),), str(photos), str(maps))
    now = {s.spec.key: s for s in inspect(links)}
    assert [k for k, s in now.items() if s.done] == ["plan", "mission", "photos", "reconstruct"]
    assert now["plan"].detail == "1 mission planned" and now["analyse"].status == "ready"
    assert has_results(links) and not has_results(Links()) and not finished(inspect(links))
    results = maps / "results"
    (results / "odm_orthophoto" / "odm_orthophoto.full.tif").write_bytes(b"x")
    (results / "analysis").mkdir()
    (results / "analysis" / "surface_summary.json").write_text("{}")
    (maps / RECORD_FILE).write_text("x")
    (maps / "export").mkdir()
    (maps / EXPORT_FILE).write_text("{}")
    assert finished(inspect(links)) and all(s.done for s in inspect(links))


def test_a_stopped_job_is_started_not_done(tmp_path: Path) -> None:
    maps = _maps(tmp_path)
    save_work(maps, WorkRecord(folder="photos", settings={}), "uploaded")
    state = inspect(Links(maps_folder=str(maps)))[3]
    assert state.status == "partial" and state.label == "Started, not finished"
    assert "Last worked on" in state.detail
    save_work(maps, WorkRecord(folder="photos", settings={}), "done")
    assert inspect(Links(maps_folder=str(maps)))[3].done
    (maps / "divi_work.json").write_text("{broken", encoding="utf-8")
    assert inspect(Links(maps_folder=str(maps)))[3].detail == "The work record could not be read"


def test_every_engine_has_one_way_in() -> None:
    assert all(callable(runner(key)) for key in KEYS)
    assert runner("report") is write_record


def test_the_report_is_one_file_that_names_every_engine_the_limits_and_the_citation(
    tmp_path: Path,
) -> None:
    maps = _maps(tmp_path)
    links = Links(("a.kmz",), (), "", str(maps))
    with pytest.raises(ReportError, match="Make maps first"):
        write_record(Links())
    assert not inspect(links)[-1].done
    stamps = {"reconstruct": {"finished": "2026-11-14 10:00", "version": "0.0.1"}}
    path = write_record(links, "Sal <block> A", stamps)
    text = path.read_text(encoding="utf-8")
    assert path == maps / RECORD_FILE and text.startswith("<!doctype html>")
    for expected in (
        "Sal &lt;block&gt; A",  # escaped
        "4 Reconstruct",
        "2026-11-14 10:00",
        "This report",
        "Missions: a.kmz",
        "not been validated against field measurements",
        "please cite it",
        "github.com/Mraz11/Divi",
        "Nothing has been measured yet",
        "odm_orthophoto.tif could not be read",  # a fake raster: named, not fatal
        "data:font/woff2;base64,",
    ):
        assert expected in text, expected
    assert "http://" not in text.replace("https://github.com", "")  # nothing fetched
    assert inspect(links)[-1].done  # writing the report is what finishes the Report engine
    blocked = Links(maps_folder=str(maps))
    path.unlink()
    path.mkdir()  # a folder where the file should go
    with pytest.raises(ReportError, match="could not be written"):
        write_record(blocked)
