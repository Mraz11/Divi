# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crowns to files: outlines for QGIS (GeoJSON, longitude/latitude) and a table (CSV)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from rasterio.features import shapes
from rasterio.transform import Affine
from rasterio.warp import transform, transform_geom

from avispria.core.crowns import Crown, CrownReport

FIELDS = (
    "id",
    "lon",
    "lat",
    "height_m",
    "area_m2",
    "diameter_m",
    "not_green",
    "lightness",
    "redness",
    "yellowness",
    "plane_residual_m",
    "structure",
    "dieback",
)


def _row(c: Crown, lon: float, lat: float) -> dict[str, Any]:
    values = {k: getattr(c, k) for k in FIELDS if hasattr(c, k)}
    return values | {"lon": round(lon, 7), "lat": round(lat, 7)}


def write_crowns(
    report: CrownReport,
    grid: Affine,
    crs: object,
    out_dir: Path,
    street: frozenset[int] | None = None,
) -> tuple[Path, Path]:
    """``crowns.geojson`` (outlines with every value) and ``crowns.csv`` (one row per crown);
    with ``street`` (ids of street trees) an ``on_street`` column is added."""
    fields = FIELDS if street is None else (*FIELDS, "on_street")
    xs, ys = grid * (
        np.array([c.col + 0.5 for c in report.crowns]),
        np.array([c.row + 0.5 for c in report.crowns]),
    )
    lons, lats = transform(crs, "EPSG:4326", list(xs), list(ys)) if report.crowns else ([], [])
    rows = {
        c.id: _row(c, lon, lat) | ({} if street is None else {"on_street": c.id in street})
        for c, lon, lat in zip(report.crowns, lons, lats, strict=True)
    }
    features = []
    for geometry, value in shapes(report.labels, mask=report.labels > 0, transform=grid):
        crown = rows.get(int(value))
        if crown is None:
            continue
        outline = transform_geom(crs, "EPSG:4326", geometry, precision=7)
        features.append({"type": "Feature", "geometry": outline, "properties": crown})
    geojson = out_dir / "crowns.geojson"
    geojson.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )
    table = out_dir / "crowns.csv"
    with table.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows.values())
    return geojson, table
