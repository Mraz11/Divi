# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Projects on the screens: starting, opening, switching, and the links written through."""

import json
from pathlib import Path

import pytest
from nicegui.testing import User

from avispria.app import project as store
from avispria.app.project import MANIFEST, ProjectError, create_project, load_project
from avispria.app.ui import drafts, projects, state
from avispria.app.ui.progress import current_progress, new_project, project_label
from avispria.app.ui.state import STATE
from uihelpers import eventually, set_text

pytestmark = [pytest.mark.anyio, pytest.mark.nicegui_main_file("tests/ui/ui_main.py")]


@pytest.fixture(autouse=True)
def projects_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "projects"
    monkeypatch.setattr(store, "default_root", lambda: root)
    return root


def _has(user: User, marker: str) -> bool:
    try:
        user.find(marker=marker)
    except AssertionError:
        return False
    return True


def test_starting_a_project_gives_it_a_folder_and_empties_the_steps(
    tmp_path: Path, projects_root: Path
) -> None:
    STATE.last_plan_files = ["old.kmz"]
    drafts.remember("plan", "x", 1)
    made = projects.start_project("Sal block A")
    assert made.folder == projects_root / "Sal-block-A" and store.is_project(made.folder)
    assert STATE.project_folder == str(made.folder) and STATE.projects == [str(made.folder)]
    assert STATE.last_plan_files == [] and drafts.DRAFTS == {}
    assert projects.current() == made and current_progress().name == "Sal block A"
    assert project_label(current_progress()) == "Project Sal block A: nothing done yet."
    second = projects.start_project("Sal block A")
    assert second.folder.name == "Sal-block-A-2"
    with pytest.raises(ProjectError, match="Give the project a name"):
        projects.start_project("  ")


def test_what_the_screens_remember_is_written_into_the_open_project(tmp_path: Path) -> None:
    made = projects.start_project("P")
    mission = made.folder / "missions" / "a.kmz"
    mission.parent.mkdir()
    mission.write_bytes(b"x")
    STATE.last_plan_files = [str(mission)]
    STATE.photo_folder = str(tmp_path)
    raw = json.loads((made.folder / MANIFEST).read_text(encoding="utf-8"))
    assert raw["plan_files"] == ["missions/a.kmz"] and raw["photo_folder"] == str(tmp_path)
    assert set(raw["engines"]) == {"plan", "photos"}
    projects.stamp("map", "cut")
    assert load_project(made.folder).engines["map"]["note"] == "cut"
    assert projects.state_of("plan").done and not projects.state_of("mission").done


def test_switching_projects_swaps_the_links_and_never_mixes_them(tmp_path: Path) -> None:
    one, two = str(tmp_path / "first.kmz"), str(tmp_path / "second.kmz")
    first = projects.start_project("First")
    STATE.last_plan_files = [one]
    second = projects.start_project("Second")
    assert STATE.last_plan_files == [] and load_project(first.folder).plan_files == [one]
    STATE.last_sent_files = [two]
    projects.open_project(first.folder)
    assert STATE.last_plan_files == [one] and STATE.last_sent_files == []
    assert load_project(second.folder).sent_files == [two]
    rows = projects.known()
    assert {r.name for r in rows} == {"First", "Second"}
    assert [r.name for r in rows if r.open] == ["First"]
    assert all(r.summary.endswith("of 8 steps done") for r in rows)


def test_closing_and_forgetting_delete_nothing(tmp_path: Path) -> None:
    made = projects.start_project("Kept")
    mission = str(tmp_path / "a.kmz")
    STATE.last_plan_files = [mission]
    new_project()  # an unnamed project: the named one keeps its links
    assert STATE.project_folder == "" and STATE.last_plan_files == []
    assert load_project(made.folder).plan_files == [mission]
    STATE.last_plan_files = ["unnamed.kmz"]  # nothing is open: nothing is written anywhere
    assert load_project(made.folder).plan_files == [mission]
    projects.stamp("plan")  # nothing to stamp without a project
    projects.open_project(made.folder)
    projects.forget(str(made.folder))
    assert STATE.projects == [] and STATE.project_folder == "" and store.is_project(made.folder)
    assert projects.current() is None and projects.known() == []


def test_a_project_whose_folder_is_gone_does_not_stop_the_program(tmp_path: Path) -> None:
    made = projects.start_project("Gone")
    (made.folder / MANIFEST).unlink()
    STATE.last_plan_files = ["a.kmz"]  # the write-through fails quietly
    assert projects.current() is None and projects.known() == []
    with pytest.raises(ProjectError):
        projects.open_project(made.folder)


def test_projects_are_remembered_between_runs(tmp_path: Path) -> None:
    kept = create_project(tmp_path / "kept", "Kept")
    path = state.settings_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {"projects": [str(kept.folder), str(tmp_path / "gone"), 3], "project_folder": "x"}
        ),
        encoding="utf-8",
    )
    STATE.load()
    try:
        assert STATE.projects == [str(kept.folder)] and STATE.project_folder == ""
        projects.open_project(kept.folder)
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["project_folder"] == str(kept.folder)
    finally:
        state.reset()


async def test_the_start_page_lists_projects_and_opens_one(user: User, tmp_path: Path) -> None:
    await user.open("/")
    await user.should_see("Projects")
    await user.should_see("A project is one flight campaign")
    await user.should_see("No flight project yet.")
    first = projects.start_project("First")
    projects.start_project("Second")
    await user.open("/")
    await user.should_see("Project Second: nothing done yet.")
    await user.should_see("First")
    await user.should_see("0 of 8 steps done")
    opens = [n for n in (0, 1) if _has(user, f"project-open-{n}")]
    assert len(opens) == 1  # only the one that is not open has an Open button
    user.find(marker=f"project-open-{opens[0]}").click()
    await eventually(lambda: STATE.project_folder == str(first.folder))


async def test_a_new_project_can_be_named_from_the_start_page(
    user: User, projects_root: Path
) -> None:
    await user.open("/")
    user.find(marker="new-project").click()
    await user.should_see("Start a new project?")
    set_text(user, "new-project-name", "Botanical garden")
    user.find(marker="new-project-confirm").click()
    await eventually(lambda: STATE.project_folder == str(projects_root / "Botanical-garden"))
    await user.should_see("Project Botanical garden: nothing done yet.", retries=100)


async def test_opening_a_folder_that_is_not_a_project_says_so(user: User, tmp_path: Path) -> None:
    made = create_project(tmp_path / "elsewhere", "Elsewhere")
    await user.open("/")
    user.find(marker="open-project").click()
    user.find(marker="open-project-confirm").click()
    await user.should_see("Choose the project's folder.")
    set_text(user, "project-folder-input", str(tmp_path))
    user.find(marker="open-project-confirm").click()
    await user.should_see("There is no Dīvi project")
    set_text(user, "project-folder-input", str(made.folder))
    user.find(marker="open-project-confirm").click()
    await eventually(lambda: STATE.project_folder == str(made.folder))
    await user.open("/")
    user.find(marker="project-forget-0").click()
    await eventually(lambda: STATE.projects == [])
