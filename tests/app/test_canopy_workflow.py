# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canopy products from a results folder: synthetic DSM, DTM and orthophoto GeoTIFFs."""

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from typer.testing import CliRunner

from avispria.app.canopy_workflow import CanopyError, describe, run_canopy
from avispria.app.cli import app

runner = CliRunner()
SIZE = 160  # 0.25 m cells: 40 m x 40 m
CRS = "EPSG:32646"
TRANSFORM = from_origin(500_000.0, 2_660_000.0, 0.25, 0.25)


def _write(path: Path, bands: np.ndarray, crs: str | None = CRS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = bands if bands.ndim == 3 else bands[None]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype=data.dtype,
        crs=crs,
        transform=TRANSFORM,
        nodata=None if data.dtype == np.uint8 else -9999.0,
    ) as dst:
        dst.write(data)


def results(tmp_path: Path, *, dtm: bool = True, ortho: bool = True) -> Path:
    """Flat ground at 60 m, one 15 m tree (green) and one 6 m roof (grey)."""
    rows, cols = np.mgrid[0:SIZE, 0:SIZE]
    ground = np.full((SIZE, SIZE), 60.0, dtype=np.float32)
    dsm = ground.copy()
    tree = (rows - 50) ** 2 + (cols - 50) ** 2 <= 30**2
    roof = (rows >= 100) & (rows < 130) & (cols >= 100) & (cols < 140)
    dsm[tree] = 75.0
    dsm[roof] = 66.0
    dsm[:2, :] = -9999.0  # no data along the top edge
    root = tmp_path / "results"
    _write(root / "odm_dem" / "dsm.tif", dsm)
    if dtm:
        _write(root / "odm_dem" / "dtm.tif", ground)
    if ortho:
        rgb = np.full((3, SIZE, SIZE), 120, dtype=np.uint8)
        rgb[1][tree] = 200  # green crown; the roof stays grey
        rgb[0][tree] = rgb[2][tree] = 60
        _write(root / "odm_orthophoto" / "odm_orthophoto.tif", rgb)
    return root


def test_canopy_from_engine_ground(tmp_path: Path) -> None:
    root = results(tmp_path)
    out = run_canopy(root, cell_m=0.5, edge_m=1.0)
    s = out.stats
    assert s.ground_source == "engine"
    assert s.height_max_m == pytest.approx(15.0, abs=0.1)
    tree_share = np.pi * (30 * 0.25) ** 2 / (40 * 40) * 100
    assert s.canopy_cover_pct == pytest.approx(tree_share, abs=3.0)
    assert s.tall_not_green_pct == pytest.approx(30 * 40 * 0.0625 / 16, abs=1.5)
    assert s.tree_tops >= 1
    with rasterio.open(out.chm_path) as src:
        assert src.crs.to_string() == CRS
        assert abs(src.res[0] - 0.5) < 1e-9
    summary = json.loads(out.summary_path.read_text(encoding="utf-8"))
    assert summary["ground_choice"]["kind"] == "engine"
    assert out.preview_path.read_bytes()[:4] == b"\x89PNG"
    assert any("canopy cover" in label for label, _ in describe(s))
    crowns = json.loads(out.crowns_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
    kinds = {f["properties"]["structure"] for f in crowns["features"]}
    assert kinds == {True, False}  # the tree and the roof
    lon, lat = crowns["features"][0]["geometry"]["coordinates"][0][0]
    assert 80 < lon < 100 and 20 < lat < 30  # longitude/latitude, not UTM metres
    assert out.crowns_table.read_text(encoding="utf-8").startswith("id,lon,lat")  # type: ignore[union-attr]
    assert summary["crowns"]["trees"] >= 1 and summary["crowns"]["structures"] >= 1


def test_canopy_without_engine_ground_or_orthophoto(tmp_path: Path) -> None:
    root = results(tmp_path, dtm=False, ortho=False)
    s = run_canopy(root, cell_m=0.5, window_m=40.0).stats
    assert s.ground_source == "estimated"
    assert "CH002" in [i.code for i in s.issues]
    assert s.tall_not_green_pct == 0.0  # nothing to tell green from grey: all tall cells count
    assert s.height_max_m == pytest.approx(15.0, abs=1.0)


def test_canopy_needs_a_surface_model_in_metres(tmp_path: Path) -> None:
    with pytest.raises(CanopyError, match="no surface model"):
        run_canopy(tmp_path)
    _write(tmp_path / "odm_dem" / "dsm.tif", np.zeros((10, 10), np.float32), crs="EPSG:4326")
    with pytest.raises(CanopyError, match="metres"):
        run_canopy(tmp_path)


def test_canopy_command(tmp_path: Path) -> None:
    root = results(tmp_path)
    result = runner.invoke(app, ["canopy", str(root), "--cell", "0.5"])
    assert result.exit_code == 0, result.output
    assert "canopy cover" in result.output and "chm.tif" in result.output
    empty = tmp_path / "empty"
    empty.mkdir()
    assert runner.invoke(app, ["canopy", str(empty)]).exit_code == 1
