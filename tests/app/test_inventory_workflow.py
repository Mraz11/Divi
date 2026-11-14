# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The tree inventory after the analysis engine: synthetic results with known trees."""

import csv
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from typer.testing import CliRunner

from avispria.app.canopy_workflow import CanopyError
from avispria.app.cli import app
from avispria.app.inventory_workflow import (
    InventoryError,
    TreeInputs,
    read_field_heights,
)
from avispria.app.surface_workflow import run_analysis
from avispria.core.biomass import BiomassInputs
from forestscene import CRS, N, _write, field_csv, scene

runner = CliRunner()


def test_the_inventory_without_extra_inputs(tmp_path: Path) -> None:
    root, _ = scene(tmp_path)
    inv = run_analysis(root, "forest").inventory
    assert inv is not None
    assert inv.quality.grade == "good" and inv.calibration.method == "none"
    assert len(inv.biomass.trees) == 9 and 3 < inv.biomass.band_one_tree < 5.5
    rows = list(csv.DictReader(inv.trees_path.read_text("utf-8").splitlines()))
    assert len(rows) == 9 and float(rows[0]["agb_low_kg"]) < float(rows[0]["agb_kg"])
    summary = json.loads(inv.summary_path.read_text("utf-8"))
    assert summary["ground_choice"]["kind"] == "engine"
    assert "not a carbon credit" in summary["biomass"]["limits"]
    assert summary["indices"]["caveat"].startswith("relative within this flight")
    assert (root / "analysis" / "indices" / "gcc.tif").is_file()
    assert (root / "analysis" / "ground_sigma.tif").is_file()
    assert inv.symptoms is not None and inv.symptoms.candidates == 0


def test_field_heights_an_outside_ground_and_a_doming_check(tmp_path: Path) -> None:
    root, ground = scene(tmp_path)
    _write(tmp_path / "lidar.tif", ground - 45.0)  # a geoid-based model, 45 m lower
    rows, cols = np.mgrid[0:N, 0:N]
    bend = 1.5 * (1 - (((rows - 99.5) ** 2 + (cols - 99.5) ** 2) / (2 * 99.5**2)))
    _write(tmp_path / "glo30.tif", ground - 20.0 - bend)  # this flight is domed against it
    inputs = TreeInputs(
        ground_file=tmp_path / "lidar.tif",
        ground_kind="lidar",
        reference_file=tmp_path / "glo30.tif",
        field_heights=field_csv(tmp_path),
        biomass=BiomassInputs(draws=300, wood_density=0.55),
    )
    outcome = run_analysis(root, "forest", trees=inputs)
    inv = outcome.inventory
    assert inv is not None
    choice = outcome.canopy.ground_choice
    assert choice is not None and choice.kind == "lidar"
    assert choice.shift_m == pytest.approx(45.0, abs=0.05)
    assert inv.quality.doming.domed and inv.quality.doming.dome_m == pytest.approx(1.5, abs=0.3)
    assert inv.quality.grade == "use with care"
    cal = inv.calibration
    assert cal.matched == 9 and cal.rmse_before_m > 1.5 and cal.rmse_after_m < 0.5
    rows_ = list(csv.DictReader(inv.trees_path.read_text("utf-8").splitlines()))
    raw, fixed = float(rows_[0]["height_model_m"]), float(rows_[0]["height_corrected_m"])
    assert fixed - raw == pytest.approx(2.0, abs=0.5)
    summary = json.loads(inv.summary_path.read_text("utf-8"))
    assert summary["assumptions"]["inputs"]["ground_file"].endswith("lidar.tif")
    assert TreeInputs.from_record(summary["assumptions"]["inputs"]) == inputs


def test_bad_inputs_are_explained(tmp_path: Path) -> None:
    root, ground = scene(tmp_path)
    bad = tmp_path / "bad.csv"
    bad.write_text("id,x,y\n1,2,3\n", encoding="utf-8")
    with pytest.raises(InventoryError, match="height column"):
        read_field_heights(bad, CRS)
    bad.write_text("id,height_m\n1,3\n", encoding="utf-8")
    with pytest.raises(InventoryError, match="lat and lon"):
        read_field_heights(bad, CRS)
    bad.write_text("lat,lon,height_m\n23.8,abc,9\n", encoding="utf-8")
    with pytest.raises(InventoryError, match="tree 1"):
        read_field_heights(bad, CRS)
    bad.write_text("", encoding="utf-8")
    with pytest.raises(InventoryError, match="no trees"):
        read_field_heights(bad, CRS)
    with pytest.raises(InventoryError, match="could not be read"):
        read_field_heights(tmp_path / "missing.csv", CRS)
    good = tmp_path / "ll.csv"
    good.write_text("lat,lon,height\n23.81,90.41,12\n", encoding="utf-8")
    ((name, x, _y, h),) = read_field_heights(good, CRS)
    assert name == "1" and h == 12 and x > 100_000
    _write(tmp_path / "same.tif", ground)
    same = TreeInputs(ground_file=tmp_path / "same.tif", reference_file=tmp_path / "same.tif")
    with pytest.raises(CanopyError, match="other than the ground model"):
        run_analysis(root, "forest", trees=same)
    with pytest.raises(CanopyError, match="outside ground model is one of"):
        run_analysis(root, "forest", trees=TreeInputs(tmp_path / "same.tif", "engine"))
    assert TreeInputs.from_record(None) == TreeInputs()


def test_the_analyse_command_takes_the_inventory_inputs(tmp_path: Path) -> None:
    root, ground = scene(tmp_path)
    _write(tmp_path / "glo30.tif", ground - 30.0)
    result = runner.invoke(
        app,
        [
            "analyse", str(root), "--field-heights", str(field_csv(tmp_path)),
            "--reference", str(tmp_path / "glo30.tif"), "--wood-density", "0.5", "--draws", "200",
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "canopy height model" in result.output and "biomass" in result.output
    assert "no doming found" in result.output


def test_compare_flights_by_rank(tmp_path: Path) -> None:
    _rows, cols = np.mgrid[0:N, 0:N]
    before = (cols / N).astype("float32")
    after = before * 0.5 + 0.2  # the whole flight duller: no change by rank
    after[:10, :10] = -1.0  # one corner lost its green
    _write(tmp_path / "a.tif", before)
    _write(tmp_path / "b.tif", after)
    out = tmp_path / "change.tif"
    result = runner.invoke(
        app,
        ["compare-flights", str(tmp_path / "a.tif"), str(tmp_path / "b.tif"), "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    with rasterio.open(out) as src:
        change = src.read(1)
    assert np.nanmedian(np.abs(change[50:, 50:])) < 1.0
    assert np.nanmean(change[:10, 10:]) < 1.0 and change[5, 5] < -0.5
