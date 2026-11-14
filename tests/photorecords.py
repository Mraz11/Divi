# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Photo metadata records for tests: fictional places at Greenwich, as in every fixture."""

from datetime import UTC, datetime, timedelta

from avispria.core.photo import PhotoRecord

T0 = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
LAT, LON = 0.0, 0.0  # Greenwich, as in every fixture
M_LAT = 1 / 110_574  # degrees per metre


def photo(
    i: int,
    seconds: float,
    north_m: float,
    *,
    speed: float = 5.0,
    exposure: float = 1 / 1000,
    width: int = 4032,
) -> PhotoRecord:
    return PhotoRecord(
        name=f"DJI_{i:04d}_D.JPG",
        time=T0 + timedelta(seconds=seconds),
        lat=LAT + north_m * M_LAT,
        lon=LON,
        relative_altitude_m=70.0,
        gimbal_pitch_deg=-90.0,
        gimbal_yaw_deg=0.0,
        speed_ms=speed,
        exposure_s=exposure,
        iso=100,
        focal_mm=6.72,
        focal_35mm=24,
        width_px=width,
        height_px=width * 3 // 4,
        model="FC9589",
        product=None,
        shutter="Electronic",
    )
