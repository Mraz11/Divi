# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Export engine: one GeoTIFF per band with a name, unit and style; layers in a GeoPackage."""

import json
import sqlite3
import struct
from contextlib import closing
from pathlib import Path

import numpy as np
import pytest
import rasterio
import shapely
from pyproj import CRS
from rasterio.transform import from_origin
from typer.testing import CliRunner

from avispria.adapters.gpkg import GpkgError, Layer, geometry_blob, write_gpkg
from avispria.app.cli import app
from avispria.app.export_rasters import BandSpec, ExportError, band_vrt, colour_range, export_band
from avispria.app.export_workflow import (
    LAYERS,
    MANIFEST,
    ExportOptions,
    describe,
    record,
    run_export,
)
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.surface_workflow import run_analysis
from avispria.core.qml import RAMPS, pseudocolor, vector
from forestscene import scene

UTM = CRS.from_epsg(32646)


@pytest.fixture
def measured(tmp_path: Path) -> Path:
    results, _ = scene(tmp_path)
    run_analysis(results, "forest", trees=TreeInputs())
    return results.parent


def _read(path: Path) -> rasterio.DatasetReader:
    return rasterio.open(path)


def test_everything_is_exported_one_band_per_file_with_names_and_styles(measured: Path) -> None:
    outcome = run_export(measured)
    folder = measured / "export"
    names = {f["file"] for f in outcome.files}
    assert {
        "bands/red.tif",
        "bands/green.tif",
        "bands/blue.tif",
        "bands/orthophoto_rgb.tif",
        "surfaces/chm.tif",
        "surfaces/dsm.tif",
        "surfaces/ground_sigma.tif",
        "analysis/landcover.tif",
        "analysis/indices/gcc.tif",
        LAYERS,
    } <= names
    with _read(folder / "surfaces" / "chm.tif") as src:
        assert src.count == 1 and src.descriptions == ("canopy height above ground",)
        assert src.units == ("m",) and src.crs.to_epsg() == 32646
        assert src.tags(ns="IMAGE_STRUCTURE")["LAYOUT"] == "COG"
    with _read(folder / "bands" / "red.tif") as src:
        assert src.count == 1 and src.dtypes == ("uint8",)
    with _read(folder / "analysis" / "landcover.tif") as src:
        assert src.colormap(1)  # the class colours travel with the file
    for tif in folder.rglob("*.tif"):
        if tif.name not in {"orthophoto_rgb.tif", "landcover.tif"}:
            assert tif.with_suffix(".qml").is_file(), tif
    manifest = json.loads((folder / MANIFEST).read_text("utf-8"))
    assert manifest["crs"] == "EPSG:32646" and len(manifest["files"]) == len(outcome.files)
    readme = (folder / "README.txt").read_text("utf-8")
    assert "EPSG:32646" in readme and "7: tree canopy" in readme and "cite" in readme
    with closing(sqlite3.connect(folder / LAYERS)) as db:
        tables = {r[0] for r in db.execute("SELECT table_name FROM gpkg_contents")}
        styles = {r[0] for r in db.execute("SELECT f_table_name FROM layer_styles")}
        trees = db.execute("SELECT COUNT(*) FROM tree_tops").fetchone()[0]
    assert {"tree_tops", "crowns", "layer_styles"} <= tables and {"tree_tops", "crowns"} <= styles
    assert trees == 9
    skipped = [line for line in describe(outcome) if line.startswith("not exported")]
    assert skipped and all(
        any(word in line for word in ("daytime heat", "sun", "albedo", "sky view"))
        for line in skipped
    )  # only the heat bands: the scene has no photo time
    assert record(outcome)["folder"] == str(folder)


def test_choices_and_missing_parts_are_respected(measured: Path) -> None:
    (measured / "results" / "analysis" / "landcover.tif").unlink()
    outcome = run_export(measured, ExportOptions(bands=False, colour=False, vectors=False))
    names = {f["file"] for f in outcome.files}
    assert not any(n.startswith("bands/") for n in names) and LAYERS not in names
    assert any("land cover classes" in s for s in outcome.skipped)
    again = run_export(measured, ExportOptions(surfaces=False, analysis=False, vectors=False))
    assert not (measured / "export" / "surfaces").exists()  # rebuilt: nothing stale left
    assert {f["file"] for f in again.files} == {
        "bands/red.tif",
        "bands/green.tif",
        "bands/blue.tif",
        "bands/orthophoto_rgb.tif",
    }


def test_nothing_to_export_says_why(tmp_path: Path) -> None:
    (tmp_path / "results").mkdir()
    with pytest.raises(ExportError, match="no georeferenced map"):
        run_export(tmp_path)
    results, _ = scene(tmp_path / "s")
    for tif in results.rglob("*.tif"):
        if "dsm" not in tif.name:
            tif.unlink()
    with pytest.raises(ExportError, match="nothing to export"):
        run_export(results.parent, ExportOptions(surfaces=False))


def _raster(path: Path, data: np.ndarray, nodata: float | None = None) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype=str(data.dtype),
        crs=UTM,
        nodata=nodata,
        transform=from_origin(500_000, 2_600_000, 0.1, 0.1),
    ) as dst:
        dst.write(data)
    return path


def test_an_alpha_band_becomes_the_mask_and_bad_bands_are_refused(tmp_path: Path) -> None:
    rgba = np.full((4, 64, 64), 120, dtype=np.uint8)
    rgba[3, :, :32] = 0  # left half outside the map
    source = _raster(tmp_path / "o.tif", rgba)
    spec = BandSpec(source, 1, tmp_path / "out" / "red.tif", "red", mask_band=4)
    assert "<MaskBand>" in band_vrt(spec)
    with _read(export_band(spec)) as src:
        mask = src.read_masks(1)
    assert mask[:, :32].max() == 0 and mask[:, 32:].min() == 255
    with pytest.raises(ExportError, match="has no band 9"):
        band_vrt(BandSpec(source, 9, tmp_path / "x.tif", "x"))
    flat = _raster(tmp_path / "f.tif", np.full((1, 8, 8), np.nan, dtype=np.float32))
    assert colour_range(BandSpec(flat, 1, tmp_path / "y.tif", "y")) == (0.0, 1.0)
    odd = _raster(tmp_path / "c.tif", np.zeros((1, 8, 8), dtype=np.complex64))
    with pytest.raises(ExportError, match="data type"):
        band_vrt(BandSpec(odd, 1, tmp_path / "z.tif", "z"))


def test_styles_are_qgis_xml() -> None:
    text = pseudocolor(0, 30, RAMPS["greens"], "m")
    assert text.startswith("<!DOCTYPE qgis") and 'type="singlebandpseudocolor"' in text
    assert text.count("<item ") == len(RAMPS["greens"]) and 'label="30 m"' in text
    assert 'maximumValue="1"' in pseudocolor(1, 1, RAMPS["grey"])  # a flat band still styles
    for kind in ("point", "line", "polygon"):
        assert "<renderer-v2" in vector(kind, "#2e7d32", "#ffffff")
    assert 'fieldName="id"' in vector("point", "#000000", "#ffffff", label="id")


def test_the_geopackage_holds_typed_columns_and_refuses_bad_names(tmp_path: Path) -> None:
    point = shapely.Point(500_000, 2_600_000)
    path = write_gpkg(
        tmp_path / "t.gpkg",
        [
            Layer(
                "pts",
                "POINT",
                [point, point],
                [
                    {"n": 1, "h": 2.5, "ok": True, "s": None},
                    {"n": 2, "h": 3.0, "ok": False, "s": "sal"},
                ],
            )
        ],
        UTM,
    )
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA application_id").fetchone()[0] == 0x47504B47
        cols = {r[1]: r[2] for r in db.execute("PRAGMA table_info(pts)")}
        srs = db.execute("SELECT srs_id FROM gpkg_geometry_columns").fetchone()[0]
        blob = db.execute("SELECT geom FROM pts").fetchone()[0]
    assert cols == {
        "fid": "INTEGER",
        "geom": "POINT",
        "n": "INTEGER",
        "h": "REAL",
        "ok": "BOOLEAN",
        "s": "TEXT",
    }
    assert srs == 32646 and blob[:2] == b"GP" and struct.unpack("<i", blob[4:8])[0] == 32646
    assert shapely.from_wkb(blob[8 + 32 :]).equals(point)
    empty = geometry_blob(shapely.Point(), 4326)
    assert empty[3] & 0b1_0000  # the empty flag
    local = write_gpkg(
        tmp_path / "l.gpkg",
        [Layer("a", "POINT", [point])],
        CRS.from_proj4("+proj=tmerc +lat_0=0 +lon_0=90 +k=1 +x_0=0 +y_0=0"),
    )
    with closing(sqlite3.connect(local)) as db:
        assert db.execute("SELECT srs_id FROM gpkg_geometry_columns").fetchone()[0] == 100_000
    for layer, message in (
        (Layer("bad name", "POINT", [point]), "use letters"),
        (Layer("a", "POINT", [point], [{}, {}]), "one row of attributes"),
        (Layer("a", "POINT", [point], [{"geom": 1}]), "reserved"),
    ):
        with pytest.raises(GpkgError, match=message):
            write_gpkg(tmp_path / "bad.gpkg", [layer], UTM)
    assert not (tmp_path / "bad.gpkg").exists() and not (tmp_path / "bad.part").exists()


def test_the_export_command(measured: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    done = runner.invoke(app, ["export", str(measured), "--no-vectors"])
    assert done.exit_code == 0 and "surfaces/chm.tif" in done.output
    assert not (measured / "export" / LAYERS).exists()
    assert runner.invoke(app, ["export", str(tmp_path / "none")]).exit_code == 2


def test_the_geopackage_file_is_closed_whatever_happens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows cannot delete or replace an open file: every connection must be closed."""
    opened: list[sqlite3.Connection] = []
    closed: list[sqlite3.Connection] = []
    connect = sqlite3.connect

    class Tracked(sqlite3.Connection):
        def close(self) -> None:
            closed.append(self)
            super().close()

    def tracked(path: object) -> sqlite3.Connection:
        found = connect(path, factory=Tracked)  # type: ignore[call-overload]
        opened.append(found)
        return found

    monkeypatch.setattr("avispria.adapters.gpkg.sqlite3.connect", tracked)
    point = shapely.Point(500_000, 2_600_000)
    write_gpkg(tmp_path / "ok.gpkg", [Layer("a", "POINT", [point])], UTM)
    with pytest.raises(GpkgError):
        write_gpkg(tmp_path / "bad.gpkg", [Layer("bad name", "POINT", [point])], UTM)
    assert len(opened) == 2 and opened == closed
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ok.gpkg"]
    monkeypatch.setattr(
        "avispria.adapters.gpkg.sqlite3.connect",
        lambda path: (_ for _ in ()).throw(sqlite3.OperationalError("unable to open")),
    )
    with pytest.raises(GpkgError, match="unable to open"):
        write_gpkg(tmp_path / "x.gpkg", [], UTM)


def test_an_export_still_open_elsewhere_is_reported_not_crashed(
    measured: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_export(measured, ExportOptions(vectors=False, analysis=False))

    def locked(path: object) -> None:
        raise PermissionError("[WinError 32] The process cannot access the file")

    monkeypatch.setattr("avispria.app.export_workflow.shutil.rmtree", locked)
    with pytest.raises(ExportError, match="Close its files in QGIS"):
        run_export(measured)
