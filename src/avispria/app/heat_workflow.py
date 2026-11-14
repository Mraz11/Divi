# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Write the relative heat exposure (``core/heat.py``) beside the other analysis outputs.

The sun is followed hour by hour on the day of the flight, at the centre of the map, from the
time and place of the photos. Without that (no photo times) there is no heat exposure, and the
summary says why.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from rasterio.warp import transform

from avispria.core.heat import HOURS, METHOD, HeatParts, heat_parts, summary
from avispria.core.indices import vegetation_mask
from avispria.core.sun import sun_position

HEAT_DIR = "heat"
BANDS = {
    "heat_index": ("relative daytime heat exposure (rank in this flight, not temperature)", ""),
    "sun_hours": ("share of 09:00-16:00 in direct sun", ""),
    "albedo": ("assumed broadband albedo (green fixed; others from relative brightness)", ""),
    "sky_view": ("sky view factor", ""),
}


def day_suns(
    record: dict[str, Any], grid: Affine, crs: object, shape: tuple[int, int]
) -> tuple[list[tuple[float, float]], str]:
    """Sun (elevation, azimuth) at each hour of HOURS on the flight day, and that day."""
    sun = record.get("sun") or {}
    day, offset = sun.get("local_date"), sun.get("utc_offset_h")
    if not isinstance(day, str) or not isinstance(offset, int | float):
        return [], ""
    x, y = grid * (shape[1] / 2, shape[0] / 2)
    (lon,), (lat,) = transform(crs, "EPSG:4326", [x], [y])
    zone = timezone(timedelta(hours=float(offset)))
    start = datetime.fromisoformat(day).replace(tzinfo=zone)
    return [sun_position(start.replace(hour=h), lat, lon) for h in HOURS], day


def _write(path: Path, values: np.ndarray, grid: Affine, crs: object, name: str) -> None:
    profile = {
        "driver": "GTiff",
        "height": values.shape[0],
        "width": values.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": grid,
        "nodata": np.nan,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(values.astype(np.float32), 1)
        dst.set_band_description(1, name)


def write_heat(
    out: Path,
    surface: np.ndarray,
    rgb: np.ndarray | None,
    cell_m: float,
    grid: Affine,
    crs: object,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Write the heat bands into ``out/heat``; returns the record for the summary."""
    if rgb is None:
        return {"made": False, "why": "there is no orthophoto to read brightness and green from"}
    suns, day = day_suns(record, grid, crs, surface.shape)
    if not suns:
        return {"made": False, "why": "the photos have no time, so the sun cannot be followed"}
    green, _ = vegetation_mask(np.nan_to_num(rgb))
    parts: HeatParts = heat_parts(surface, rgb, green, cell_m, suns)
    folder = out / HEAT_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for key, (name, _) in BANDS.items():
        _write(
            folder / f"{key}.tif",
            getattr(parts, "index" if key == "heat_index" else key),
            grid,
            crs,
            name,
        )
    return {"made": True, "day": day, "method": METHOD, **summary(parts)}
