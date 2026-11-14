# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The list of DJI camera drones, and what Dīvi can do for each."""

from pathlib import Path

import pytest

from avispria.adapters.profiles import load_profiles
from avispria.app.ui.pages.plan_form import drone_note
from avispria.app.workflow import PlanBlockedError, PlanOptions, run_plan
from avispria.core.camera import gsd_m

PROFILES = load_profiles()
NOT_LISTED = ("avata", "fpv", "neo", "thermal", "multispectral", "m3t", "m3m")


def test_the_list_is_the_native_waypoint_drones() -> None:
    assert list(PROFILES) == [
        "mavic-4-pro", "mavic-3-pro", "mavic-3", "mavic-3-classic", "air-3s", "air-3",
        "mini-5-pro", "mini-4-pro", "lito-x1",
    ]  # fmt: skip
    for key, profile in PROFILES.items():
        assert profile.name.startswith("DJI ")
        assert not any(word in (key + profile.name).lower() for word in NOT_LISTED)


def test_every_drone_has_sane_camera_numbers() -> None:
    for profile in PROFILES.values():
        assert profile.max_speed_ms >= 10
        for cam in profile.modes.values():
            # at 100 m a consumer drone's camera sees 1.5 to 4 cm per pixel
            assert 0.008 < gsd_m(cam, 100.0) < 0.045, profile.key
            assert cam.readout_s <= 0.06
        if profile.mechanical_shutter:
            assert all(c.readout_s <= 0.001 for c in profile.modes.values())


def test_only_dji_fly_drones_get_missions(tmp_path: Path) -> None:
    flying = {k for k, p in PROFILES.items() if p.flies_dji_fly_missions}
    assert flying == set(PROFILES)
    inspire = other_app(tmp_path)["other"]
    assert "no Dīvi missions yet" in inspire.label and PROFILES["air-3"].label == "DJI Air 3"
    assert "cannot make a mission" in drone_note(inspire)
    assert "Waypoint Pro" in drone_note(inspire) and "Mechanical shutter" in drone_note(inspire)
    assert drone_note(PROFILES["lito-x1"]) == ""
    with pytest.raises(PlanBlockedError, match="AVI005"):
        run_plan(tmp_path / "a", tmp_path / "t", inspire, PlanOptions(0, 0), tmp_path, 0)


OTHER = (
    '[other]\nname = "DJI Other"\nmax_speed_ms = 20\ndrone_enum = 0\nwaypoint_limit = 99\n'
    'mission_app = "{app}"\nmechanical_shutter = true\n[other.modes.a]\nsensor_width_mm = 36\n'
    "sensor_height_mm = 24\nfocal_mm = 24\nimage_width_px = 8192\nimage_height_px = 5456\n"
    "min_interval_s = 2\nreadout_s = 0.001\n"
)


def other_app(tmp_path: Path, app: str = "waypoint-pro") -> dict:  # type: ignore[type-arg]
    extra = tmp_path / "other.toml"
    extra.write_text(OTHER.format(app=app), encoding="utf-8")
    return load_profiles(extra)


def test_a_bad_mission_app_is_refused(tmp_path: Path) -> None:
    extra = tmp_path / "mine.toml"
    extra.write_text(
        '[x]\nname = "DJI X"\nmax_speed_ms = 10\ndrone_enum = 0\nwaypoint_limit = 9\n'
        'mission_app = "litchi"\n[x.modes.a]\nsensor_width_mm = 1\nsensor_height_mm = 1\n'
        "focal_mm = 1\nimage_width_px = 1\nimage_height_px = 1\nmin_interval_s = 1\n"
        "readout_s = 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="mission_app"):
        load_profiles(extra)
