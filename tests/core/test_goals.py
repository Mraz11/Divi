# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""From what you want to measure to how to fly."""

import pytest
from typer.testing import CliRunner

from avispria.adapters.profiles import load_profiles
from avispria.app.cli import app
from avispria.core.camera import gsd_m
from avispria.core.goals import GOALS, MAX_AGL_M, MIN_CLEARANCE_M, advise, describe

CAM = load_profiles()["lito-x1"].modes["12mp"]
runner = CliRunner()


def test_every_goal_gives_settings_or_a_reason() -> None:
    for key in GOALS:
        a = advise(key, None, CAM)
        assert a.gsd_m > 0 and 0.5 <= a.side < a.front <= 0.9
        assert a.agl_m <= MAX_AGL_M
        assert gsd_m(CAM, a.agl_m) == pytest.approx(a.gsd_m, rel=0.02)
        assert describe(a)


def test_general_mapping_keeps_every_later_analysis_open() -> None:
    general = advise("general", None, CAM)
    assert next(iter(GOALS)) == "general" and general.reachable
    for key in ("crowns", "heights", "cover", "symptoms", "buildings"):
        other = advise(key, None, CAM)
        assert general.gsd_m <= other.gsd_m + 1e-9 and general.front >= other.front
    assert "when the maps are made" in describe(general)


def test_small_things_need_finer_resolution_and_leaves_cannot_be_reached() -> None:
    seedlings = advise("plants", 0.05, CAM)
    assert seedlings.gsd_m == pytest.approx(0.01) and seedlings.reachable
    small_crowns = advise("crowns", 0.6, CAM)  # 0.6 m / 24 = 2.5 cm
    assert small_crowns.gsd_m == pytest.approx(0.025) and small_crowns.agl_m < MAX_AGL_M
    assert advise("crowns", 3.0, CAM).agl_m == MAX_AGL_M  # capped: finer is just better
    lesions = advise("lesions", None, CAM)
    assert not lesions.reachable and lesions.agl_m < MIN_CLEARANCE_M
    assert describe(lesions).startswith("Not reachable from a mapping flight")
    assert "close-up photos" in describe(lesions)
    assert advise("symptoms", 2.0, CAM).gsd_m == pytest.approx(0.03)
    with pytest.raises(ValueError, match="unknown goal"):
        advise("weather", 1.0, CAM)
    with pytest.raises(ValueError, match="more than zero"):
        advise("plants", 0.0, CAM)


def test_the_advise_command() -> None:
    ok = runner.invoke(app, ["advise", "plants", "--size", "0.1"])
    assert ok.exit_code == 0 and "cm per pixel" in ok.output
    assert runner.invoke(app, ["advise", "lesions"]).exit_code == 1
    assert runner.invoke(app, ["advise", "weather"]).exit_code == 2
    assert runner.invoke(app, ["advise", "crowns", "--aircraft", "x"]).exit_code == 2
