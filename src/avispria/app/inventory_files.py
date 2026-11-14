# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The tree inventory's files: field heights in, trees.csv and rasters out."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import Affine

from avispria.core.biomass import StandBiomass
from avispria.core.symptoms import SymptomReport

HEIGHT_NAMES = ("height_m", "height", "h", "tree_height_m")


class InventoryError(ValueError):
    """An input of the inventory cannot be used; the message says why."""


def read_field_heights(path: Path, crs: object) -> list[tuple[str, float, float, float]]:
    """Field trees from a CSV: lat/lon (WGS 84) or x/y (the map's coordinates), and a height."""
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except OSError as exc:
        raise InventoryError(f"the field heights could not be read: {exc}") from None
    if not rows:
        raise InventoryError(f"{path.name} has no trees in it")
    cols = {c.strip().lower(): c for c in rows[0]}
    hcol = next((cols[n] for n in HEIGHT_NAMES if n in cols), None)
    if hcol is None:
        raise InventoryError(f"{path.name} needs a height column ({', '.join(HEIGHT_NAMES)})")
    geographic = "lat" in cols and "lon" in cols
    if not geographic and not ("x" in cols and "y" in cols):
        raise InventoryError(f"{path.name} needs lat and lon columns (or x and y)")
    move = Transformer.from_crs("EPSG:4326", crs, always_xy=True) if geographic else None
    out = []
    for n, row in enumerate(rows, start=1):
        try:
            a, b = (
                (row[cols["lon"]], row[cols["lat"]]) if move else (row[cols["x"]], row[cols["y"]])
            )
            x, y = move.transform(float(a), float(b)) if move else (float(a), float(b))
            h = float(row[hcol])
        except (ValueError, TypeError):
            raise InventoryError(f"{path.name}, tree {n}: a number could not be read") from None
        name = str(row.get(cols.get("id", ""), "") or n)
        out.append((name, float(x), float(y), h))
    return out


def write_raster(path: Path, values: np.ndarray, grid: Affine, crs: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype="float32",
        crs=crs,
        transform=grid,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(values.astype(np.float32), 1)


TREE_FIELDS = (
    "id",
    "lon",
    "lat",
    "height_model_m",
    "height_corrected_m",
    "crown_diameter_m",
    "agb_kg",
    "agb_low_kg",
    "agb_high_kg",
    "agb_chave_kg",
    "co2e_kg",
    "co2e_low_kg",
    "co2e_high_kg",
    "gcc",
    "gcc_z",
    "symptom_candidate",
    "symptom_reason",
)


def write_trees(
    out: Path,
    trees: list[Any],
    xs: np.ndarray,
    ys: np.ndarray,
    crs: object,
    heights: np.ndarray,
    corrected: np.ndarray,
    stand: StandBiomass | None,
    symptoms: SymptomReport | None,
) -> Path:
    to_lonlat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lons, lats = to_lonlat.transform(xs, ys) if len(trees) else ([], [])
    by_id = {s.crown_id: s for s in symptoms.crowns} if symptoms else {}
    path = out / "trees.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TREE_FIELDS)
        writer.writeheader()
        for k, c in enumerate(trees):
            b, s = (None if stand is None else stand.trees[k]), by_id.get(c.id)
            writer.writerow(
                {
                    "id": c.id,
                    "lon": round(float(lons[k]), 7),
                    "lat": round(float(lats[k]), 7),
                    "height_model_m": round(float(heights[k]), 2),
                    "height_corrected_m": round(float(corrected[k]), 2),
                    "crown_diameter_m": c.diameter_m,
                    "agb_kg": None if b is None else b.jucker.median,
                    "agb_low_kg": None if b is None else b.jucker.low,
                    "agb_high_kg": None if b is None else b.jucker.high,
                    "agb_chave_kg": None if b is None else b.chave.median,
                    "co2e_kg": None if b is None else b.co2e.median,
                    "co2e_low_kg": None if b is None else b.co2e.low,
                    "co2e_high_kg": None if b is None else b.co2e.high,
                    "gcc": None if s is None else s.gcc,
                    "gcc_z": None if s is None else s.gcc_z,
                    "symptom_candidate": None if s is None else s.candidate,
                    "symptom_reason": None if s is None else s.reason,
                }
            )
    return path
