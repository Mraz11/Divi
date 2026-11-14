# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""`avispria analyse` on the synthetic town written as engine results (GeoTIFFs)."""

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from typer.testing import CliRunner

from avispria.app.cli import app
from avispria.app.surface_workflow import analysis_step, describe_analysis, run_analysis
from cityscene import CELL, city

runner = CliRunner()
CRS = "EPSG:32646"
GRID = from_origin(500_000.0, 2_660_000.0, CELL, CELL)


def _write(path: Path, data: np.ndarray, dtype: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bands = data if data.ndim == 3 else data[None]
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=bands.shape[1],
        width=bands.shape[2],
        count=bands.shape[0],
        dtype=dtype,
        crs=CRS,
        transform=GRID,
    ) as dst:
        dst.write(bands.astype(dtype))


def town_results(tmp_path: Path, sun: bool = True) -> Path:
    s = city()
    root = tmp_path / "out" / "results"
    _write(root / "odm_dem" / "dsm.tif", s.dsm, "float32")
    _write(root / "odm_dem" / "dtm.tif", s.dsm - s.height, "float32")
    _write(root / "odm_orthophoto" / "odm_orthophoto.tif", np.moveaxis(s.rgb, -1, 0), "uint8")
    if sun:
        record = {
            "sun": {
                "elevation_deg": 50.0,
                "azimuth_deg": 170.0,
                "local_date": "2026-04-15",
                "utc_offset_h": 6.0,
            }
        }
        (tmp_path / "out" / "avispria_provenance.json").write_text(json.dumps(record), "utf-8")
    return root


def test_the_town_from_files(tmp_path: Path) -> None:
    root = town_results(tmp_path)
    out = run_analysis(root, "urban")
    m = out.result.metrics
    assert m["buildings"] == 2 and m["street_trees"] == 5 and m["street_tree_gaps"] == 1
    assert m["street_shade_pct"] is not None  # the sun at 14:00 on 15 April was worked out
    summary = json.loads(out.summary_path.read_text("utf-8"))
    assert (
        summary["profile"] == "urban" and 50 < summary["sun_for_street_shade"][0] < 60
    )  # 14:00, 24 N, mid-April
    analysis = root / "analysis"
    for name in ("landcover.tif", "confidence.tif", "landcover_preview.png", "roads.geojson"):
        assert (analysis / name).is_file(), name
    with rasterio.open(out.landcover_path) as src:
        assert src.colormap(1)[8][:3] == (200, 70, 60)  # buildings in their colour
        assert src.read(1).max() <= 11
    buildings = json.loads((analysis / "buildings.geojson").read_text("utf-8"))["features"]
    assert sorted(f["properties"]["roof"] for f in buildings) == ["flat", "pitched"]
    lon, lat = buildings[0]["geometry"]["coordinates"][0][0]
    assert 90 < lon < 100 and 20 < lat < 30
    crowns = (root / "canopy" / "crowns.csv").read_text("utf-8")
    assert "on_street" in crowns.splitlines()[0] and crowns.count("True") >= 5
    canopy = json.loads((root / "canopy" / "canopy_summary.json").read_text("utf-8"))
    assert canopy["crowns"]["trees"] == m["trees"]  # one set of crowns everywhere
    assert any("street trees" in label for label, _ in describe_analysis(m))


def test_forest_profile_and_no_sun(tmp_path: Path) -> None:
    root = town_results(tmp_path, sun=False)
    out = run_analysis(root, "forest")
    assert "roads" not in out.result.metrics and out.result.shadow is None
    assert not (root / "analysis" / "roads.geojson").exists()


def test_step_and_command(tmp_path: Path) -> None:
    infos: list[str] = []
    warns: list[str] = []
    assert analysis_step(tmp_path, "urban", infos.append, warns.append) is None  # no DSM
    root = town_results(tmp_path)
    assert analysis_step(root, "urban", infos.append, warns.append) is not None
    assert any(line.startswith("buildings:") for line in infos)
    result = runner.invoke(app, ["analyse", str(root), "--profile", "urban"])
    assert result.exit_code == 0, result.output
    assert "street trees" in result.output and "landcover.tif" in result.output
    assert runner.invoke(app, ["analyse", str(root), "--profile", "ocean"]).exit_code == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert runner.invoke(app, ["analyse", str(empty)]).exit_code == 1


@pytest.mark.parametrize("bad", [{"sun": {"elevation_deg": "x"}}, {"sun": None}, []])
def test_odd_provenance_is_ignored(tmp_path: Path, bad: object) -> None:
    root = town_results(tmp_path, sun=False)
    (root.parent / "avispria_provenance.json").write_text(json.dumps(bad), "utf-8")
    assert run_analysis(root, "urban").result.metrics["street_shade_pct"] is None
