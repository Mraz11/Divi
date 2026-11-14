# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A synthetic forest written as engine results: nine trees of known height on a gentle slope."""

import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

CRS = "EPSG:32646"
CELL = 0.5
N = 200  # 100 m x 100 m
GRID = from_origin(500_000.0, 2_660_000.0, CELL, CELL)
TREES = [(30 + 45 * (k % 3), 30 + 45 * (k // 3), 8.0 + 2.5 * k) for k in range(9)]


def _write(path: Path, data: np.ndarray, dtype: str = "float32") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bands = data if data.ndim == 3 else data[None]
    with rasterio.open(
        path, "w", driver="GTiff", height=bands.shape[1], width=bands.shape[2],
        count=bands.shape[0], dtype=dtype, crs=CRS, transform=GRID,
    ) as dst:  # fmt: skip
        dst.write(bands.astype(dtype))


def scene(tmp_path: Path) -> tuple[Path, np.ndarray]:
    rows, cols = np.mgrid[0:N, 0:N]
    ground = 60.0 + 0.02 * cols
    dsm = ground.copy()
    rgb = np.zeros((3, N, N))
    rgb[:] = np.array([150, 125, 95])[:, None, None]  # bare soil
    for r, c, h in TREES:
        crown = (rows - r) ** 2 + (cols - c) ** 2 <= 12**2
        dome = h - 0.01 * ((rows - r) ** 2 + (cols - c) ** 2)
        dsm = np.where(crown, np.maximum(dsm, ground + dome), dsm)
        rgb[:, crown] = np.array([60, 150, 55])[:, None]
    root = tmp_path / "out" / "results"
    _write(root / "odm_dem" / "dsm.tif", dsm)
    _write(root / "odm_dem" / "dtm.tif", ground)
    _write(root / "odm_orthophoto" / "odm_orthophoto.tif", rgb, "uint8")
    return root, ground


def field_csv(tmp_path: Path, bias: float = 2.0) -> Path:
    path = tmp_path / "field.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "x", "y", "height_m"])
        for k, (r, c, h) in enumerate(TREES):
            x, y = GRID * (c + 0.5, r + 0.5)
            w.writerow([f"T{k}", x + 0.4, y - 0.3, h + bias])  # the field says 2 m taller
    return path


def area_file(tmp_path: Path, rows: tuple[int, int], cols: tuple[int, int], kind: str) -> Path:
    """A rectangle of grid cells as a KML or GeoJSON in longitude/latitude."""
    to_ll = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    corners = [GRID * (c, r) for r, c in ((rows[0], cols[0]), (rows[0], cols[1]),
                                           (rows[1], cols[1]), (rows[1], cols[0]))]  # fmt: skip
    ring = [to_ll.transform(x, y) for x, y in corners]
    ring.append(ring[0])
    if kind == "kml":
        path = tmp_path / "area.kml"
        coords = " ".join(f"{x},{y}" for x, y in ring)
        path.write_text(
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Polygon><outerBoundaryIs>'
            f"<LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs>"
            "</Polygon></Placemark></kml>",
            encoding="utf-8",
        )
        return path
    path = tmp_path / "area.geojson"
    path.write_text(json.dumps({"type": "Polygon", "coordinates": [ring]}), encoding="utf-8")
    return path
