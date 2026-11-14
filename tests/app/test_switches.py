# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Switched-off analyses are neither saved nor reported; the rest is unchanged."""

import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from avispria.app.cli import app
from avispria.app.inventory_workflow import TreeInputs, describe_inventory
from avispria.app.surface_workflow import describe_analysis, run_analysis
from avispria.core.analyses import KEYS
from forestscene import scene

ALL_OFF = TreeInputs(off=KEYS)


def test_everything_switched_off_leaves_the_core(tmp_path: Path) -> None:
    results, _ = scene(tmp_path)
    outcome = run_analysis(results, "urban", trees=ALL_OFF)
    out = results / "analysis"
    for name in (
        "landcover.tif",
        "confidence.tif",
        "landcover_preview.png",
        "buildings.geojson",
        "roads.geojson",
        "indices",
    ):
        assert not (out / name).exists(), name
    assert (results / "canopy" / "chm.tif").is_file() and (out / "trees.csv").is_file()
    assert (out / "ground_sigma.tif").is_file()  # the quality checks always run
    summary = json.loads((out / "surface_summary.json").read_text("utf-8"))
    assert summary["switched_off"] == list(KEYS)
    assert set(summary["metrics"]) == {"area_m2", "tree_canopy_pct", "trees", "dieback_candidates"}
    inventory = json.loads((out / "inventory_summary.json").read_text("utf-8"))
    assert inventory["biomass"] is None and inventory["indices"] is None
    assert inventory["symptoms"] is None and inventory["assumptions"]["inputs"]["off"] == list(KEYS)
    with (out / "trees.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and all(r["agb_kg"] == "" and r["height_model_m"] for r in rows)
    assert [label for label, _ in describe_analysis(outcome.result.metrics)] == [
        "tree canopy",
        "trees outlined",
    ]
    assert outcome.inventory is not None
    labels = [label for label, _ in describe_inventory(outcome.inventory)]
    assert "biomass (above ground)" not in labels and "visible symptoms" not in labels


def test_switches_survive_the_work_record() -> None:
    again = TreeInputs.from_record(json.loads(json.dumps(TreeInputs(off=("roads",)).record())))
    assert again.off == ("roads",)
    assert TreeInputs.from_record({"ground_kind": "lidar"}).off == ()


def test_the_analyse_command_switches_analyses_off(tmp_path: Path) -> None:
    results, _ = scene(tmp_path)
    runner = CliRunner()
    done = runner.invoke(app, ["analyse", str(results), "--off", "landcover", "--off", "biomass"])
    assert done.exit_code == 0, done.output
    assert not (results / "analysis" / "landcover.tif").exists()
    assert (results / "analysis" / "indices").is_dir()
    wrong = runner.invoke(app, ["analyse", str(results), "--off", "lidar"])
    assert wrong.exit_code == 2 and "no analysis called lidar" in wrong.output
