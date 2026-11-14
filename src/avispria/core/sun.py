# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where the sun is: the flying window of a plan, and the light the photos were taken in.

The first real flight was flown at sunset (sun 3.4 to 1.0 degrees up): shadows 17 to 57 times
the height of the trees hid most of the ground, the camera chose slow shutters, and colours were
orange. Sun elevation therefore decides how far canopy heights and colour indices can be trusted,
and is computed for every plan and every set of photos.

The solar position is the US Naval Observatory's low-precision formula (good to about 0.1 degree
between 1950 and 2050, ample for shadows); no refraction is applied.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone

from avispria.core.photo import PhotoRecord
from avispria.core.safety import Issue

GOOD_SUN_DEG = 35.0  # shadows shorter than 1.4x the tree height: ground and gaps show
LOW_SUN_DEG = 25.0  # below this, warn: shadows longer than 2.1x the tree height
VERY_LOW_SUN_DEG = 10.0  # shadows longer than 5.7x the tree height: most ground hidden
J2000 = datetime(2000, 1, 1, 12, tzinfo=UTC)


def sun_position(when: datetime, lat: float, lon: float) -> tuple[float, float]:
    """Sun elevation and azimuth in degrees (azimuth clockwise from north) at an aware time."""
    if when.tzinfo is None:
        raise ValueError("the time must carry its time zone")
    d = (when - J2000) / timedelta(days=1)
    g = math.radians((357.529 + 0.98560028 * d) % 360)
    q = (280.459 + 0.98564736 * d) % 360
    ecl_lon = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)
    tilt = math.radians(23.439 - 0.00000036 * d)
    ra = math.atan2(math.cos(tilt) * math.sin(ecl_lon), math.cos(ecl_lon))
    dec = math.asin(math.sin(tilt) * math.sin(ecl_lon))
    sidereal_h = (18.697374558 + 24.06570982441908 * d) % 24
    hour_angle = math.radians(sidereal_h * 15 + lon - math.degrees(ra))
    phi = math.radians(lat)
    elevation = math.asin(
        math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(hour_angle)
    )
    azimuth = math.atan2(
        -math.sin(hour_angle),
        math.tan(dec) * math.cos(phi) - math.sin(phi) * math.cos(hour_angle),
    )
    return math.degrees(elevation), math.degrees(azimuth) % 360


def shadow_ratio(elevation_deg: float) -> float:
    """Shadow length per metre of height; infinite at or below the horizon."""
    return math.inf if elevation_deg <= 0 else 1 / math.tan(math.radians(elevation_deg))


@dataclass(frozen=True)
class Window:
    start: datetime  # aware, in the zone asked for
    end: datetime
    noon: datetime
    noon_elevation_deg: float
    min_elevation_deg: float


def good_window(
    day: date, lat: float, lon: float, zone: timezone, min_elevation_deg: float = GOOD_SUN_DEG
) -> Window | None:
    """The part of ``day`` (in ``zone``) with the sun at least ``min_elevation_deg`` up.

    None when the sun never gets that high (winter at high latitudes): the noon light is then the
    best there is.
    """
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    times = [start + timedelta(minutes=2 * k) for k in range(721)]
    elevations = [sun_position(t, lat, lon)[0] for t in times]
    best = max(range(len(times)), key=elevations.__getitem__)
    good = [t for t, e in zip(times, elevations, strict=True) if e >= min_elevation_deg]
    if not good:
        return None
    return Window(good[0], good[-1], times[best], elevations[best], min_elevation_deg)


def utc_offset_for(lon: float, computer: timedelta | None = None) -> timedelta:
    """The likely UTC offset of a camera clock at ``lon``: the computer's own offset when it is
    within two hours of the longitude's solar zone (true for a PC in the same country), else the
    solar zone (longitude / 15, whole hours)."""
    solar = timedelta(hours=round(lon / 15))
    if computer is not None and abs(computer - solar) <= timedelta(hours=2):
        return computer
    return solar


@dataclass(frozen=True)
class PhotoLight:
    elevation_deg: float | None  # median over the photos
    azimuth_deg: float | None
    lowest_deg: float | None
    time_basis: str  # how the camera's clock was turned into UTC
    issues: list[Issue] = field(default_factory=list)
    local_date: str | None = None  # the flight day, ISO, on the camera's clock
    utc_offset_h: float | None = None  # the offset used


def photo_light(records: Sequence[PhotoRecord], computer: timedelta | None = None) -> PhotoLight:
    """The sun during the photos. DJI clocks are local time with no zone: see ``utc_offset_for``."""
    usable = [r for r in records if r.time is not None and r.lat is not None and r.lon is not None]
    if not usable:
        return PhotoLight(None, None, None, "no photo times")
    lon = statistics.median(r.lon for r in usable if r.lon is not None)
    offset = utc_offset_for(lon, computer)
    aware = any(r.time.tzinfo is not None for r in usable)  # type: ignore[union-attr]
    basis = (
        "time zone written in the photos"
        if aware
        else f"camera clock read as UTC{_hours(offset)} (no zone in the photos)"
    )
    suns = []
    for r in usable:
        t = r.time
        assert t is not None and r.lat is not None and r.lon is not None
        t = t if t.tzinfo else t.replace(tzinfo=timezone(offset))
        suns.append(sun_position(t, r.lat, r.lon))
    elev = statistics.median(e for e, _ in suns)
    az = statistics.median(a for _, a in suns)
    lowest = min(e for e, _ in suns)
    issues = []
    if elev < LOW_SUN_DEG:
        ratio = shadow_ratio(elev)
        shadows = (
            "the sun was down or at the horizon"
            if math.isinf(ratio)
            else f"shadows were {ratio:.0f}x as long as the trees are tall"
        )
        level = "very low" if elev < VERY_LOW_SUN_DEG else "low"
        issues.append(
            Issue(
                "warning",
                "QA021",
                f"the sun was {level} ({elev:.0f} degrees up): {shadows}, so much of the ground "
                "is hidden, the camera needs slow shutters and colours are warm; canopy heights "
                "and colour measures from this flight are less reliable",
            )
        )
    middle = sorted(r.time for r in usable if r.time is not None)[len(usable) // 2]
    return PhotoLight(
        round(elev, 1),
        round(az, 1),
        round(lowest, 1),
        basis,
        issues,
        middle.date().isoformat(),
        round(offset.total_seconds() / 3600, 2),
    )


def local_offset() -> timedelta | None:
    """This computer's own UTC offset now."""
    return datetime.now().astimezone().utcoffset()


def _hours(offset: timedelta) -> str:
    minutes = round(offset.total_seconds() / 60)
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def describe_window(window: Window | None, day: date) -> str:
    """One line for the plan and the Fly screen."""
    if window is None:
        return (
            f"On {day:%d %b} the sun never gets {GOOD_SUN_DEG:.0f} degrees up here: fly as close "
            "to midday as you can."
        )
    return (
        f"Best light on {day:%d %b}: {window.start:%H:%M} to {window.end:%H:%M} (sun at least "
        f"{window.min_elevation_deg:.0f} degrees up; highest {window.noon_elevation_deg:.0f} "
        f"degrees at {window.noon:%H:%M}). Shadows are then at most "
        f"{shadow_ratio(window.min_elevation_deg):.1f}x the tree height."
    )
