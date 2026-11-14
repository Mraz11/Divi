# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Report engine: the words, the pictures and the one file, from what the engines left."""

import io
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from avispria.app.engines import Links
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.report_data import LONGEST_PX, gather, ortho_picture
from avispria.app.report_html import render
from avispria.app.report_workflow import write_record
from avispria.app.surface_workflow import run_analysis
from avispria.core.report_text import (
    LIMITS,
    findings,
    key_numbers,
    methods,
    num,
    ranged,
    references,
)
from forestscene import field_csv, scene

PROVENANCE = {
    "preset": "standard",
    "engine": {"engine": "odm", "engine_version": "3.5.4"},
    "reconstruction": {
        "photos_total": 212,
        "photos_placed": 210,
        "reprojection_px": 0.81,
        "gsd_cm_measured": 2.1,
    },
    "capture_qa": {
        "stats": {"photos_total": 212, "gsd_cm_median": 2.05, "altitude_m_median": 74.0},
        "issues": [{"code": "QA005", "message": "a 9 s gap between photos"}],
    },
    "task": {"processing_s": 5400},
    "options_sent": {"dsm": True, "dtm": True},
    "inputs": [{"file": "DJI_0001.JPG"}],
    "outputs": [{"file": "results/odm_dem/dsm.tif"}],
}


def test_numbers_and_ranges_read_well() -> None:
    assert num(1234.567) == "1,234.6" and num(3, 0) == "3" and num(None) == "—"
    assert num(True) == "—"  # a flag is not a number
    spread = {"median": 7606.0, "low": 4117.6, "high": 14976.3}
    assert ranged(spread, "t", 2, 0.001) == "7.61 t (95% range 4.12\u201314.98 t)"
    assert ranged({"median": 5.0}, "m") == "5.0 m" and ranged(None) == "—"
    assert ranged({"median": "x"}) == "—"


def test_only_what_was_done_is_described() -> None:
    assert methods(None, None, None, None) == [] and key_numbers(None, None, None) == []
    assert references(None, None) == [] and findings(None, None, None) == []
    parts = dict(methods(PROVENANCE, None, None, None))
    text = parts["Photos and reconstruction"][0]
    assert text.startswith("212 photos (median ground detail 2.05 cm, median height 74.0 m)")
    assert "odm 3.5.4, preset 'standard'" in text and "210 photos were placed" in text
    assert references(PROVENANCE, None)[0].startswith("OpenDroneMap")
    bare = dict(methods({"preset": "fast"}, None, None, None))["Photos and reconstruction"][0]
    assert bare == "The photos were processed with the map engine, preset 'fast'."
    assert dict(
        methods(None, None, {"method": "land cover by rules", "crown_detector": "x"}, None)
    )["Land cover"] == ["Land cover by rules. Crown detector: x."]
    assert len(LIMITS) == 4


@pytest.fixture
def measured(tmp_path: Path) -> Path:
    results, _ = scene(tmp_path)
    run_analysis(results, "forest", trees=TreeInputs(field_heights=field_csv(tmp_path)))
    (results.parent / "divi_provenance.json").write_text(json.dumps(PROVENANCE), "utf-8")
    return results.parent


def test_a_measured_project_gets_its_numbers_methods_and_references(measured: Path) -> None:
    data = gather(Links(maps_folder=str(measured)), "Sal")
    assert data.missing == [] and next(c for c, _ in data.pictures) == "Orthophoto"
    assert len(data.pictures) == 3 and data.states[-1].detail == "This report"
    rows = {
        what: value for what, value, _ in key_numbers(data.canopy, data.surface, data.inventory)
    }
    assert rows["Area measured"].endswith(" ha") and "95% range" in rows["Above-ground biomass"]
    assert rows["Quality grade of the height model"] in {"good", "fair", "poor"}
    assert "tree canopy" in rows["Land cover"]
    parts = dict(methods(data.provenance, data.canopy, data.surface, data.inventory))
    assert set(parts) == {
        "Photos and reconstruction",
        "Canopy height model",
        "Land cover",
        "Trees, biomass and carbon",
    }
    assert not parts["Canopy height model"][0].count("Ground: ground:")
    assert "Calibrated on" in parts["Trees, biomass and carbon"][0]
    assert "97.5th percentiles" in parts["Trees, biomass and carbon"][1]
    assert any("Jucker" in r for r in references(data.provenance, data.inventory))
    assert findings(data.canopy, data.surface, data.inventory)  # the doming note at least
    html = render(data)
    for expected in (
        "Canopy cover",
        "Biomass per hectare",
        "QA005: a 9 s gap",
        "212 photos",
        "Processing time: 5,400 s",
        "dsm, dtm",
        'class="legend"',
        "Chave",
    ):
        assert expected in html, expected


def test_unreadable_files_are_named_not_fatal(measured: Path) -> None:
    results = measured / "results"
    (results / "canopy" / "canopy_summary.json").write_text("{broken", "utf-8")
    (results / "analysis" / "surface_summary.json").write_text("[1, 2]", "utf-8")
    (results / "analysis" / "landcover_preview.png").write_bytes(b"not a picture")
    data = gather(Links(maps_folder=str(measured)))
    assert data.missing == ["canopy_summary.json", "surface_summary.json", "landcover_preview.png"]
    html = write_record(Links(maps_folder=str(measured))).read_text("utf-8")
    assert "canopy_summary.json could not be read" in html and "Unnamed project" in html


def _ortho(path: Path, data: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype=str(data.dtype),
        crs="EPSG:32646",
        transform=from_origin(500_000, 2_600_000, 1, 1),
    ) as dst:
        dst.write(data)
    return path


@pytest.mark.parametrize("bands", [1, 3, 4])
def test_ortho_pictures_are_small_whatever_the_raster(tmp_path: Path, bands: int) -> None:
    big = np.random.default_rng(0).integers(0, 4000, (bands, 300, 3000), dtype=np.uint16)
    png = ortho_picture(_ortho(tmp_path / "o.tif", big))
    with Image.open(io.BytesIO(png)) as image:
        assert max(image.size) <= LONGEST_PX and image.mode == "RGBA"


def test_a_project_without_maps_has_no_files_to_read() -> None:
    data = gather(Links(plan_files=("a.kmz",)))
    assert data.provenance is None and data.pictures == [] and "Unnamed project" in render(data)
