# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Export engine: the maps and measurements as files made for QGIS and other programs.

Everything goes to ``<maps folder>/export``:

* ``bands/``: the orthophoto's red, green and blue, one file each, plus the full-colour orthophoto;
* ``surfaces/``: surface model, ground model, canopy height model, ground uncertainty;
* ``analysis/``: land cover (with its colour table), its confidence, the colour index bands;
* ``divi_layers.gpkg``: tree tops, crowns, buildings and roads, editable, styled for QGIS;
* ``README.txt`` and ``export_manifest.json``: what each file is, its unit and where it came from.

Every raster is a Cloud-Optimised GeoTIFF in the map's own coordinate system, with a QGIS style
(``.qml``) beside it. What a project does not have (a switched-off analysis, an uncut map) is
simply left out and listed.
"""

from __future__ import annotations

import csv
import json
import shutil
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import shapely
from pyproj import CRS, Transformer

from avispria.adapters.gpkg import GpkgError, Layer, write_gpkg
from avispria.app.export_rasters import BandSpec, ExportError, export_band, export_whole
from avispria.core.landcover import CLASSES
from avispria.core.qml import vector
from avispria.core.version import __version__

EXPORT_DIR = "export"
MANIFEST = "export_manifest.json"
LAYERS = "divi_layers.gpkg"
ORTHO = "odm_orthophoto/odm_orthophoto.tif"
INDEX_TEXT = "relative within this flight; not comparable with other flights"
HEAT_BANDS: dict[str, tuple[str, str, tuple[float, float] | None]] = {
    "heat_index": (
        "relative daytime heat exposure, 0-1 rank in this flight (not temperature)",
        "magma",
        (0.0, 1.0),
    ),
    "sun_hours": ("share of 09:00-16:00 in direct sun (0-1)", "viridis", (0.0, 1.0)),
    "albedo": ("assumed broadband albedo (green fixed, others from brightness)", "grey", None),
    "sky_view": ("sky view factor (0-1)", "grey", (0.0, 1.0)),
}


@dataclass(frozen=True)
class ExportOptions:
    bands: bool = True  # red, green and blue as separate files
    colour: bool = True  # the full-colour orthophoto too
    surfaces: bool = True  # DSM, DTM, CHM, ground uncertainty
    analysis: bool = True  # land cover, confidence, index bands
    vectors: bool = True  # the GeoPackage


@dataclass
class ExportOutcome:
    folder: Path
    files: list[dict[str, str]] = field(default_factory=list)  # file, what, unit, source
    skipped: list[str] = field(default_factory=list)  # what the project does not have


def _spec(results: Path, rel: str, out: Path, name: str, **kw: Any) -> BandSpec:
    return BandSpec(results / rel, kw.pop("band", 1), out, name, **kw)


def raster_jobs(results: Path, folder: Path, options: ExportOptions) -> list[tuple[str, Any]]:
    """(what it is, a BandSpec or a (source, target) pair to copy whole), in export order."""
    jobs: list[tuple[str, Any]] = []
    if options.bands:
        for band, colour in enumerate(("red", "green", "blue"), start=1):
            jobs.append(
                (
                    f"orthophoto {colour} band (0-255, camera colours)",
                    _spec(
                        results,
                        ORTHO,
                        folder / "bands" / f"{colour}.tif",
                        f"{colour} (orthophoto)",
                        band=band,
                        fixed=(0.0, 255.0),
                        mask_band=4,
                    ),
                )
            )
    if options.colour:
        jobs.append(
            (
                "full-colour orthophoto (RGB and alpha)",
                (results / ORTHO, folder / "bands" / "orthophoto_rgb.tif"),
            )
        )
    if options.surfaces:
        jobs += [
            (
                "surface model: height above sea level of the top surface (m)",
                _spec(
                    results,
                    "odm_dem/dsm.tif",
                    folder / "surfaces" / "dsm.tif",
                    "surface height (DSM)",
                    unit="m",
                    ramp="terrain",
                ),
            ),
            (
                "ground model from the map engine (m)",
                _spec(
                    results,
                    "odm_dem/dtm.tif",
                    folder / "surfaces" / "dtm.tif",
                    "ground height (DTM)",
                    unit="m",
                    ramp="terrain",
                ),
            ),
            (
                "canopy height model: height above ground (m), from Dīvi's checked ground",
                _spec(
                    results,
                    "canopy/chm.tif",
                    folder / "surfaces" / "chm.tif",
                    "canopy height above ground",
                    unit="m",
                    ramp="greens",
                    stretch=(0.0, 99.0),
                ),
            ),
            (
                "uncertainty of the ground under each cell (1 sd, m)",
                _spec(
                    results,
                    "analysis/ground_sigma.tif",
                    folder / "surfaces" / "ground_sigma.tif",
                    "ground uncertainty (1 sd)",
                    unit="m",
                    ramp="magma",
                ),
            ),
        ]
    if options.analysis:
        jobs += [
            (
                "land cover classes (colour table inside; class names in README.txt)",
                (results / "analysis/landcover.tif", folder / "analysis" / "landcover.tif"),
            ),
            (
                "confidence of the land cover (0-100)",
                _spec(
                    results,
                    "analysis/confidence.tif",
                    folder / "analysis" / "confidence.tif",
                    "land cover confidence",
                    unit="%",
                    fixed=(0.0, 100.0),
                ),
            ),
        ]
        for key, (what, ramp, fixed) in HEAT_BANDS.items():
            jobs.append(
                (
                    what,
                    BandSpec(
                        results / "analysis" / "heat" / f"{key}.tif",
                        1,
                        folder / "analysis" / "heat" / f"{key}.tif",
                        what,
                        ramp=ramp,
                        fixed=fixed,
                    ),
                )
            )
        indices = results / "analysis" / "indices"
        for path in sorted(indices.glob("*.tif")) if indices.is_dir() else []:
            ramp = "grey" if path.stem == "vegetation_mask" else "diverging"
            jobs.append(
                (
                    f"colour index {path.stem} ({INDEX_TEXT})",
                    BandSpec(
                        path, 1, folder / "analysis" / "indices" / path.name, path.stem, ramp=ramp
                    ),
                )
            )
    return jobs


def _to_map(crs: CRS) -> Callable[[shapely.Geometry], shapely.Geometry]:
    move = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    return lambda g: shapely.transform(g, lambda xy: _stack(move.transform(xy[:, 0], xy[:, 1])))


def _stack(xy: tuple[Any, Any]) -> Any:
    return np.column_stack(xy)


def _geojson_layer(
    path: Path,
    name: str,
    kind: str,
    to_map: Callable[[shapely.Geometry], shapely.Geometry],
    style: str,
    description: str,
) -> Layer | None:
    if not path.is_file():
        return None
    found = json.loads(path.read_text(encoding="utf-8"))
    features = [f for f in found.get("features", []) if f.get("geometry")]
    geoms = [to_map(shapely.geometry.shape(f["geometry"])) for f in features]
    rows = [
        {k: v for k, v in (f.get("properties") or {}).items() if k.lower() not in {"fid", "geom"}}
        for f in features
    ]
    if kind == "POLYGON" and any(g.geom_type == "MultiPolygon" for g in geoms):
        kind = "MULTIPOLYGON"
        geoms = [shapely.multipolygons([g]) if g.geom_type == "Polygon" else g for g in geoms]
    return Layer(name, kind, geoms, rows, description, style)


def _number(text: str) -> Any:
    if text in {"", "None"}:
        return None
    if text in {"True", "False"}:
        return text == "True"
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _trees_layer(path: Path, crs: CRS) -> Layer | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8", newline="") as f:
        rows = [{k: _number(v) for k, v in row.items()} for row in csv.DictReader(f)]
    move = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    points = [shapely.Point(*move.transform(r["lon"], r["lat"])) for r in rows]
    style = vector("point", "#2e7d32", "#ffffff", 2.4, "id")
    return Layer("tree_tops", "POINT", points, rows, "tree tops with heights and biomass", style)


def vector_layers(results: Path, crs: CRS) -> list[Layer]:
    to_map = _to_map(crs)
    found = [
        _trees_layer(results / "analysis" / "trees.csv", crs),
        _geojson_layer(
            results / "canopy" / "crowns.geojson",
            "crowns",
            "POLYGON",
            to_map,
            vector("polygon", "", "#39ff14", 0.5),
            "tree crowns",
        ),
        _geojson_layer(
            results / "analysis" / "buildings.geojson",
            "buildings",
            "POLYGON",
            to_map,
            vector("polygon", "#7a96aa", "#3f5d72", 0.4),
            "building outlines",
        ),
        _geojson_layer(
            results / "analysis" / "roads.geojson",
            "roads",
            "POLYGON",
            to_map,
            vector("polygon", "#dbb241", "#765900", 0.3),
            "road outlines",
        ),
    ]
    return [layer for layer in found if layer is not None and layer.geometries]


def map_crs(results: Path) -> CRS:
    for rel in (ORTHO, "odm_dem/dsm.tif", "canopy/chm.tif"):
        if (results / rel).is_file():
            with rasterio.open(results / rel) as src:
                if src.crs:
                    return CRS.from_wkt(src.crs.to_wkt())
    raise ExportError("there is no georeferenced map in this folder to export")


def run_export(maps_folder: Path, options: ExportOptions | None = None) -> ExportOutcome:
    """Export everything the project has; raises ExportError when there is nothing to export."""
    options = options or ExportOptions()
    results = maps_folder / "results"
    crs = map_crs(results)
    folder = maps_folder / EXPORT_DIR
    if folder.exists():
        try:
            shutil.rmtree(folder)  # an export is rebuilt each time: nothing stale stays behind
        except OSError as exc:  # on Windows, a file open in QGIS cannot be deleted
            raise ExportError(
                f"the earlier export could not be replaced ({exc}). Close its files in QGIS or "
                "any other program, then export again."
            ) from None
    outcome = ExportOutcome(folder)
    for what, job in raster_jobs(results, folder, options):
        source = job.source if isinstance(job, BandSpec) else job[0]
        if not source.is_file():
            outcome.skipped.append(f"{what}: not in this project")
            continue
        target = export_band(job) if isinstance(job, BandSpec) else export_whole(*job)
        unit = job.unit if isinstance(job, BandSpec) else ""
        outcome.files.append(_entry(target, folder, what, unit, source, results))
    if options.vectors:
        layers = vector_layers(results, crs)
        if layers:
            try:
                write_gpkg(folder / LAYERS, layers, crs)
            except GpkgError as exc:
                raise ExportError(str(exc)) from None
            names = ", ".join(layer.name for layer in layers)
            outcome.files.append(
                {"file": LAYERS, "what": f"editable layers: {names}", "unit": "", "source": ""}
            )
        else:
            outcome.skipped.append("vector layers: no trees, crowns, buildings or roads yet")
    if not outcome.files:
        raise ExportError("nothing to export: make maps first (step 4)")
    write_notes(outcome, crs)
    return outcome


def _entry(
    target: Path, folder: Path, what: str, unit: str, source: Path, results: Path
) -> dict[str, str]:
    return {
        "file": target.relative_to(folder).as_posix(),
        "what": what,
        "unit": unit,
        "source": source.relative_to(results).as_posix(),
    }


def write_notes(outcome: ExportOutcome, crs: CRS) -> None:
    record = {
        "tool": {"name": "divi", "version": __version__},
        "made": time.strftime("%Y-%m-%d %H:%M"),
        "crs": crs.to_string(),
        "files": outcome.files,
        "skipped": outcome.skipped,
    }
    (outcome.folder / MANIFEST).write_text(json.dumps(record, indent=2), encoding="utf-8")
    lines = [
        f"Dīvi {__version__} export, {record['made']}",
        f"Coordinate system of every file: {crs.to_string()} ({crs.name})",
        "",
        "Open any .tif or the .gpkg in QGIS (drag it in): the styles load with it.",
        "Every .tif is a Cloud-Optimised GeoTIFF: one band each, except orthophoto_rgb.tif and",
        "landcover.tif. The .gpkg layers can be edited in QGIS and saved in place.",
        "",
        "Files:",
    ]
    lines += [f"  {f['file']}: {f['what']}" for f in outcome.files]
    if any(f["file"] == "analysis/landcover.tif" for f in outcome.files):
        lines += ["", "Land cover classes (value: class):"]
        lines += [f"  {k}: {name}" for k, (name, _) in CLASSES.items()]
    if outcome.skipped:
        lines += ["", "Not exported:"] + [f"  {s}" for s in outcome.skipped]
    lines += ["", "If you publish results made with these files, please cite Dīvi (CITATION.cff)."]
    (outcome.folder / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def describe(outcome: ExportOutcome) -> list[str]:
    return [f"{f['file']}: {f['what']}" for f in outcome.files] + [
        f"not exported: {s}" for s in outcome.skipped
    ]


def record(outcome: ExportOutcome) -> dict[str, Any]:
    return asdict(outcome) | {"folder": str(outcome.folder)}
