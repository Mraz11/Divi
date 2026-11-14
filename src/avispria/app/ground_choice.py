# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Choose the ground model for the canopy heights, best source first (core/ground_sources.py).

The candidates: an outside ground model given by the person (LiDAR, leaf-off flight, survey or
a global model), the engine's ground from this flight, and Dīvi's own estimate. The ground the
flight saw (where the surface meets this flight's own ground) decides how open the area is, and
so whether a global model beats this flight's own ground; an outside model is then moved up or
down to meet the flight where the ground was seen.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject

from avispria.core.canopy import estimate_ground
from avispria.core.ground_sources import (
    OUTSIDE_KINDS,
    GroundChoice,
    align,
    rank,
    seen_ground,
)


def onto(
    path: Path,
    shape: tuple[int, int],
    transform: Affine,
    crs: object,
    band: int = 1,
    resampling: Resampling = Resampling.bilinear,
) -> np.ndarray:
    """One band of the raster at ``path`` resampled onto the given grid (NaN = no data)."""
    out = np.full(shape, np.nan)
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, band),
            destination=out,
            dst_transform=transform,
            dst_crs=crs,
            dst_nodata=np.nan,
            resampling=resampling,
        )
    return out


def choose_ground(
    results_dir: Path,
    dsm: np.ndarray,
    transform: Affine,
    crs: object,
    window_m: float,
    ground_file: Path | None = None,
    ground_kind: str = "lidar",
) -> tuple[np.ndarray, GroundChoice, np.ndarray]:
    """The ground to use, the choice made, and where this flight saw its ground."""
    cell = abs(transform.a)
    candidates: dict[str, np.ndarray] = {}
    if ground_file is not None:
        if ground_kind not in OUTSIDE_KINDS:
            raise ValueError(
                f"an outside ground model is one of: {', '.join(OUTSIDE_KINDS)} "
                f"(not {ground_kind!r})"
            )
        outside = onto(ground_file, dsm.shape, transform, crs)
        if not np.isfinite(outside).any():
            raise ValueError(f"{ground_file.name} does not cover the mapped area")
        candidates[ground_kind] = outside
    engine = results_dir / "odm_dem" / "dtm.tif"
    if engine.is_file():
        candidates["engine"] = onto(engine, dsm.shape, transform, crs)
    if "engine" not in candidates:
        try:
            candidates["estimated"] = estimate_ground(dsm, cell, window_m)
        except ValueError:
            if not candidates:
                raise
    own = candidates.get("engine", candidates.get("estimated"))
    seen = seen_ground(dsm, own) if own is not None else np.zeros(dsm.shape, bool)
    area = max(1, int(np.isfinite(dsm).sum()))
    seen_pct = float(seen.sum() / area * 100)
    ranking = rank(list(candidates), seen_pct)
    kind = ranking[0]
    ground, shift, cells = candidates[kind], 0.0, 0
    if kind in OUTSIDE_KINDS:
        ground, shift, cells = align(ground, dsm, seen)
        ground = np.where(np.isfinite(ground), ground, own if own is not None else np.nan)
    choice = GroundChoice(
        kind,
        ("lidar", "leaf-off", "survey", "engine", "global", "estimated").index(kind) + 1,
        tuple(ranking),
        round(shift, 3),
        cells,
        round(seen_pct, 1),
        "",
    )
    return ground, choice, seen
