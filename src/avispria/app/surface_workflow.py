# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""`avispria analyse`: everything Dīvi measures, from one results folder, for one profile.

1. canopy height (``run_canopy``: DSM minus ground, canopy numbers, ``canopy/chm.tif``);
2. the analysis engine (``core/surface.py``) on that height, the orthophoto's colours and the
   sun of the photos: land cover, trees, buildings, roads and street trees;
3. files in ``analysis/``: ``landcover.tif`` (class per cell, colour table), ``confidence.tif``,
   ``landcover_preview.png``, ``buildings.geojson``, ``roads.geojson``,
   ``surface_summary.json``; the tree crowns go to ``canopy/crowns.geojson`` (one set of crowns
   for every screen, with street trees marked).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from rasterio.features import shapes
from rasterio.transform import Affine
from rasterio.warp import transform, transform_geom

from avispria.app.canopy_workflow import (
    CANOPY_DIR,
    CanopyError,
    CanopyOutcome,
    _colour,
    _onto,
    crowns_record,
    run_canopy,
)
from avispria.app.crown_boxes import boxes_for
from avispria.app.crowns_output import write_crowns
from avispria.app.heat_workflow import write_heat
from avispria.app.inventory_workflow import (
    InventoryError,
    InventoryOutcome,
    TreeInputs,
    describe_inventory,
    run_inventory,
)
from avispria.app.paths import provenance_file
from avispria.core.analyses import on, trim_metrics
from avispria.core.landcover import CLASSES
from avispria.core.profiles import profile
from avispria.core.sun import sun_position
from avispria.core.surface import SurfaceResult, analyse_surface

ANALYSIS_DIR = "analysis"
SHADE_HOUR = 14  # street shade is reported for 14:00, the hottest hour, on the flight day


@dataclass(frozen=True)
class AnalysisOutcome:
    result: SurfaceResult
    canopy: CanopyOutcome
    summary_path: Path
    landcover_path: Path
    preview_path: Path
    inventory: InventoryOutcome | None = None


def _provenance(results_dir: Path) -> dict[str, Any]:
    try:
        found = json.loads(provenance_file(results_dir.parent).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def _suns(
    record: dict[str, Any], grid: Affine, crs: object, shape: tuple[int, int]
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    """The sun of the photos, and the sun at SHADE_HOUR on the flight day at the map's centre."""
    sun = record.get("sun") or {}
    elev, az = sun.get("elevation_deg"), sun.get("azimuth_deg")
    at_photos = (
        (float(elev), float(az)) if isinstance(elev, int | float) and az is not None else None
    )
    day, offset = sun.get("local_date"), sun.get("utc_offset_h")
    if not isinstance(day, str) or not isinstance(offset, int | float):
        return at_photos, None
    x, y = grid * (shape[1] / 2, shape[0] / 2)
    (lon,), (lat,) = transform(crs, "EPSG:4326", [x], [y])
    zone = timezone(timedelta(hours=float(offset)))
    when = datetime.fromisoformat(day).replace(hour=SHADE_HOUR, tzinfo=zone)
    return at_photos, sun_position(when, lat, lon)


def _write_raster(path: Path, values: np.ndarray, grid: Affine, crs: object, colours: bool) -> None:
    profile_ = {
        "driver": "GTiff",
        "height": values.shape[0],
        "width": values.shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": crs,
        "transform": grid,
        "nodata": 0,
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **profile_) as dst:
        dst.write(values, 1)
        if colours:
            dst.write_colormap(1, {k: (*rgb, 255) for k, (_, rgb) in CLASSES.items()})


def _polygons(
    labels: np.ndarray, records: dict[int, dict[str, Any]], grid: Affine, crs: object, path: Path
) -> Path:
    features = []
    for geometry, value in shapes(labels.astype(np.int32), mask=labels > 0, transform=grid):
        props = records.get(int(value))
        if props is not None:
            outline = transform_geom(crs, "EPSG:4326", geometry, precision=7)
            features.append({"type": "Feature", "geometry": outline, "properties": props})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), "utf-8")
    return path


def run_analysis(
    results_dir: Path,
    profile_name: str = "forest",
    *,
    cell_m: float = 0.5,
    sun_record: dict[str, Any] | None = None,
    trees: TreeInputs | None = None,
) -> AnalysisOutcome:
    """Every product for ``results_dir`` under the named profile; raises CanopyError.

    The sun of the photos comes from ``sun_record`` (as `process` writes it in the provenance
    record), else from the provenance file next to the results."""
    trees = trees or TreeInputs()
    off = trees.off
    prof = replace(
        profile(profile_name),
        buildings=profile(profile_name).buildings and on("buildings", off),
        roads=profile(profile_name).roads and on("roads", off),
    )
    canopy = run_canopy(
        results_dir,
        cell_m=cell_m,
        window_m=prof.ground_window_m,
        crowns=False,
        ground_file=trees.ground_file,
        ground_kind=trees.ground_kind,
    )
    with rasterio.open(canopy.chm_path) as src:
        height = src.read(1).astype(float)
        grid, crs = src.transform, src.crs
    cell = abs(grid.a)
    dsm = _onto(results_dir / "odm_dem" / "dsm.tif", height.shape, grid, crs)
    rgb = _colour(results_dir, height.shape, grid, crs)
    record = {"sun": sun_record} if sun_record is not None else _provenance(results_dir)
    sun, shade_at = _suns(record, grid, crs, height.shape)
    if not on("street_shade", off):
        shade_at = None
    boxes, detector = boxes_for(results_dir, grid, height.shape) if trees.deepforest else ([], "")
    result = analyse_surface(
        height,
        cell,
        prof,
        dsm=dsm,
        rgb=None if rgb is None else np.nan_to_num(rgb),
        sun=sun,
        shade_at=shade_at,
        ground_estimated=canopy.stats.ground_source == "estimated",
        tree_boxes=boxes or None,
    )
    result = replace(result, metrics=trim_metrics(result.metrics, off))
    out = results_dir / ANALYSIS_DIR
    out.mkdir(parents=True, exist_ok=True)
    landcover = out / "landcover.tif"
    preview = out / "landcover_preview.png"
    if on("landcover", off):
        _write_raster(landcover, result.cover.classes, grid, crs, colours=True)
        _write_raster(out / "confidence.tif", result.cover.confidence, grid, crs, colours=False)
        palette = np.array([CLASSES[k][1] for k in sorted(CLASSES)], dtype=np.uint8)
        Image.fromarray(palette[result.cover.classes]).save(preview)
    buildings = {b.id: asdict(b) for b in result.buildings}
    if prof.buildings:
        _polygons(result.cover.buildings, buildings, grid, crs, out / "buildings.geojson")
    if result.roads is not None:
        roads = {r.id: asdict(r) for r in result.roads.roads}
        _polygons(result.roads.labels, roads, grid, crs, out / "roads.geojson")
    street = None if result.roads is None else result.roads.street_tree_ids
    write_crowns(result.crowns, grid, crs, results_dir / CANOPY_DIR, street)
    canopy_record = json.loads(canopy.summary_path.read_text("utf-8"))
    canopy_record |= {"sun_elevation_deg": None if sun is None else sun[0]}
    canopy_record["crowns"] = crowns_record(result.crowns)
    canopy.summary_path.write_text(json.dumps(canopy_record, indent=2), "utf-8")
    summary = {
        "profile": prof.name,
        "cell_m": cell,
        "sun_at_photos": sun,
        "sun_for_street_shade": shade_at,
        "metrics": result.metrics,
        "switched_off": list(off),
        "classes": {str(k): name for k, (name, _) in CLASSES.items()},
        "buildings": list(buildings.values()),
        "roads": [] if result.roads is None else [asdict(r) for r in result.roads.roads],
        "issues": [asdict(i) for i in result.issues if on("landcover", off) or i.code != "LC001"],
        "crown_detector": detector or "not used (height model only)",
        "method": "land cover by rules on height above ground, roughness, colour (excess green, "
        "CIE Lab) and shadow predicted from the 3D model and the sun; see docs/field/analysis.md",
    }
    if on("heat", off):
        summary["heat"] = write_heat(out, dsm, rgb, cell, grid, crs, record)
    summary_path = out / "surface_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=_plain), encoding="utf-8")
    inventory = None
    if canopy.grids is not None and canopy.ground_choice is not None:
        try:
            inventory = run_inventory(
                results_dir,
                canopy.grids,
                canopy.ground_choice,
                result.crowns,
                None if rgb is None else np.nan_to_num(rgb),
                grid,
                crs,
                None if sun is None else sun[0],
                trees,
            )
        except InventoryError as exc:
            raise CanopyError(str(exc)) from exc
    return AnalysisOutcome(result, canopy, summary_path, landcover, preview, inventory)


def _plain(value: object) -> object:
    """numpy numbers and sets in the summary, as JSON."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, frozenset | set):
        return sorted(value)
    raise TypeError(f"not JSON: {type(value).__name__}")


def describe_analysis(metrics: dict[str, Any]) -> list[tuple[str, str]]:
    """The headline numbers in plain words (CLI and log); switched-off ones are absent."""
    rows = [("tree canopy", f"{metrics['tree_canopy_pct']:.0f}% of the area")]
    if "green_pct" in metrics:
        rows.append(
            ("all green (trees, shrubs, grass, green roofs)", f"{metrics['green_pct']:.0f}%")
        )
        rows.append(("sealed (roofs, paving, vehicles)", f"{metrics['impervious_pct']:.0f}%"))
    rows.append(("trees outlined", f"{metrics['trees']}"))
    if "buildings" in metrics:
        rows.append(
            ("buildings", f"{metrics['buildings']} ({metrics['built_area_m2']:.0f} m2 of roof)")
        )
    if metrics.get("rooftop_green_m2"):
        rows.append(("rooftop vegetation", f"{metrics['rooftop_green_m2']:.0f} m2"))
    if "roads" in metrics:
        rows.append(
            (
                "roads and street trees",
                f"{metrics['road_length_m']:.0f} m of road, {metrics['street_trees']} street "
                f"trees ({metrics['street_trees_per_100m']:.1f} per 100 m), "
                f"{metrics['street_tree_gaps']} planting gap(s)",
            )
        )
    if metrics.get("street_shade_pct") is not None:
        rows.append(("street shade from trees at 14:00", f"{metrics['street_shade_pct']:.0f}%"))
    if "confidence_mean" in metrics:
        rows.append(("confidence of the land cover", f"{metrics['confidence_mean']:.0f} of 100"))
    return rows


def analysis_step(
    results_dir: Path,
    profile_name: str,
    info: Callable[[str], None],
    warn: Callable[[str], None],
    sun_record: dict[str, Any] | None = None,
    trees: TreeInputs | None = None,
) -> AnalysisOutcome | None:
    """After processing; never fails the job."""
    if not (results_dir / "odm_dem" / "dsm.tif").is_file():
        return None
    try:
        outcome = run_analysis(results_dir, profile_name, sun_record=sun_record, trees=trees)
    except (CanopyError, OSError, ValueError) as exc:
        warn(f"analysis not made: {exc}")
        return None
    for label, value in describe_analysis(outcome.result.metrics):
        info(f"{label}: {value}")
    if outcome.inventory is not None:
        for label, value in describe_inventory(outcome.inventory):
            info(f"{label}: {value}" if label else value)
    for issue in [*outcome.result.issues, *outcome.canopy.stats.issues]:
        warn(f"{issue.code}: {issue.message}")
    return outcome
