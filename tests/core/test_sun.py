# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sun position checked against published values; fictional photo places."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from avispria.core.sun import (
    describe_window,
    good_window,
    photo_light,
    shadow_ratio,
    sun_position,
    utc_offset_for,
)
from photorecords import photo  # a 70 m photo at Greenwich


def test_equinox_noon_at_greenwich_and_solstice_at_the_tropic() -> None:
    elev, az = sun_position(datetime(2026, 3, 20, 12, 7, tzinfo=UTC), 0.0, 0.0)
    assert elev == pytest.approx(90.0, abs=0.5)
    elev, _ = sun_position(datetime(2026, 6, 21, 12, 2, tzinfo=UTC), 23.44, 0.0)
    assert elev == pytest.approx(90.0, abs=0.5)
    # London midsummer noon: 90 - 51.5 + 23.4 = 61.9 degrees, due south
    elev, az = sun_position(datetime(2026, 6, 21, 12, 2, tzinfo=UTC), 51.5, 0.0)
    assert elev == pytest.approx(61.9, abs=0.3) and az == pytest.approx(180, abs=2)
    morning = sun_position(datetime(2026, 6, 21, 6, 0, tzinfo=UTC), 51.5, 0.0)
    assert 60 < morning[1] < 110  # east-ish
    with pytest.raises(ValueError):
        sun_position(datetime(2026, 1, 1), 0, 0)


def test_shadow_ratio() -> None:
    assert shadow_ratio(45) == pytest.approx(1.0)
    assert shadow_ratio(0) == float("inf")


def test_good_window() -> None:
    zone = timezone(timedelta(hours=6))
    w = good_window(date(2026, 11, 7), 23.81, 90.41, zone)
    assert w is not None
    assert (w.start.hour, w.end.hour) in {(9, 14)}  # about 09:10 to 14:10 local
    assert w.noon_elevation_deg == pytest.approx(49.5, abs=1.0)
    assert "Best light on 07 Nov" in describe_window(w, date(2026, 11, 7))
    arctic = good_window(date(2026, 12, 21), 69.6, 18.9, UTC)
    assert arctic is None and "never gets" in describe_window(arctic, date(2026, 12, 21))


def test_offset_from_the_computer_or_the_longitude() -> None:
    assert utc_offset_for(90.41, timedelta(hours=6)) == timedelta(hours=6)
    assert utc_offset_for(77.0, timedelta(hours=5, minutes=30)) == timedelta(hours=5, minutes=30)
    assert utc_offset_for(90.41, timedelta(hours=-5)) == timedelta(hours=6)  # PC elsewhere
    assert utc_offset_for(-74.0) == timedelta(hours=-5)


def test_photo_light_at_sunset_and_noon() -> None:
    noon = [
        replace(photo(k, 2.0 * k, 10.0 * k), time=datetime(2026, 3, 20, 12, 7)) for k in range(3)
    ]
    light = photo_light(noon, timedelta(0))
    assert light.elevation_deg == pytest.approx(90, abs=1) and light.issues == []
    assert "UTC+00:00" in light.time_basis
    dusk = [replace(p, time=datetime(2026, 3, 20, 17, 50)) for p in noon]
    low = photo_light(dusk, timedelta(0))
    assert [i.code for i in low.issues] == ["QA021"] and "very low" in low.issues[0].message
    aware = [replace(p, time=datetime(2026, 3, 20, 15, 0, tzinfo=UTC)) for p in noon]
    assert photo_light(aware).time_basis == "time zone written in the photos"
    assert photo_light([]).elevation_deg is None
