# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.core.citation import REPOSITORY, citation
from avispria.core.pipeline import (
    AFTER_FLIGHT,
    ENGINES,
    KEYS,
    STATUS_TEXT,
    TOTAL,
    blocked_by,
    complete,
    diagram,
    engine,
    status,
)


def test_there_are_eight_engines_in_the_order_a_project_goes() -> None:
    assert KEYS == (
        "plan",
        "mission",
        "photos",
        "reconstruct",
        "map",
        "analyse",
        "export",
        "report",
    )
    assert [e.number for e in ENGINES] == list(range(1, 9)) and TOTAL == 8
    assert (
        diagram()
        == "Plan -> Mission -> Photo check -> Reconstruct -> Map -> Analyse -> Export -> Report"
    )
    assert all(e.task.endswith(".") and e.makes for e in ENGINES)
    assert set(AFTER_FLIGHT) < set(KEYS)


def test_an_engine_only_needs_engines_before_it() -> None:
    for spec in ENGINES:
        for need in spec.needs:
            assert engine(need).number < spec.number
    with pytest.raises(KeyError, match="no engine called 'fly'"):
        engine("fly")


def test_the_state_of_an_engine_comes_from_what_is_done() -> None:
    assert blocked_by("analyse", set()) == ("reconstruct",)
    assert blocked_by("analyse", {"reconstruct"}) == ()
    assert status("plan", finished=False, started=False, done=set()) == "ready"
    assert status("mission", finished=False, started=False, done=set()) == "waiting"
    assert status("mission", finished=False, started=False, done={"plan"}) == "ready"
    assert status("reconstruct", finished=False, started=True, done=set()) == "partial"
    assert status("report", finished=True, started=True, done=set()) == "done"
    assert set(STATUS_TEXT) == {"done", "partial", "ready", "waiting"}


def test_a_project_is_complete_without_the_optional_cut() -> None:
    everything = set(KEYS)
    assert complete(everything) and complete(everything - {"map"})
    assert not complete(everything - {"report"})
    assert [e.key for e in ENGINES if e.optional] == ["map"]


def test_the_citation_names_the_version_and_where_to_find_it() -> None:
    text = citation("1.2.3", 2027)
    assert "version 1.2.3" in text and "(2027)" in text and text.endswith(REPOSITORY)
