# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path

import pytest
import rasterio

from avispria.app.engines import Links
from avispria.app.export_workflow import run_export
from avispria.app.figure import draw, layers
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.report_workflow import write_record
from avispria.app.surface_workflow import run_analysis
from avispria.core.figure_spec import FigureSpec
from forestscene import scene

SUN = {"elevation_deg": 50, "azimuth_deg": 160, "local_date": "2026-12-15", "utc_offset_h": 6}


@pytest.fixture
def timed(tmp_path: Path) -> Path:
    results, _ = scene(tmp_path)
    (results.parent / "divi_provenance.json").write_text(json.dumps({"sun": SUN}), "utf-8")
    return results


def _heat(results: Path) -> dict:
    found = json.loads((results / "analysis" / "surface_summary.json").read_text("utf-8"))
    return found["heat"]


def test_heat_bands_are_written_and_described(timed: Path) -> None:
    run_analysis(timed, "forest", trees=TreeInputs())
    heat = _heat(timed)
    assert heat["made"] and heat["day"] == "2026-12-15" and heat["sun_positions"] == 8
    assert "not temperature" in heat["method"]
    assert heat["index_mean_green"] < heat["index_mean_not_green"]
    for name in ("heat_index", "sun_hours", "albedo", "sky_view"):
        with rasterio.open(timed / "analysis" / "heat" / f"{name}.tif") as src:
            assert src.dtypes == ("float32",) and src.descriptions[0]
    exported = {f["file"] for f in run_export(timed.parent).files}
    assert "analysis/heat/heat_index.tif" in exported
    assert {"heat_index", "sun_hours", "sky_view"} <= set(layers(timed))
    draw(FigureSpec("heat_index", width_mm=85, dpi=72), timed)
    report = write_record(Links(maps_folder=str(timed.parent))).read_text("utf-8")
    assert "Heat exposure (relative)" in report and "thermal camera" in report


def test_no_heat_without_photo_times_or_when_switched_off(timed: Path, tmp_path: Path) -> None:
    run_analysis(timed, "forest", trees=TreeInputs(off=("heat",)))
    assert "heat" not in json.loads(
        (timed / "analysis" / "surface_summary.json").read_text("utf-8")
    )
    bare, _ = scene(tmp_path / "bare")
    run_analysis(bare, "forest", trees=TreeInputs())
    assert _heat(bare) == {
        "made": False,
        "why": "the photos have no time, so the sun cannot be followed",
    }
    assert not (bare / "analysis" / "heat").exists()
