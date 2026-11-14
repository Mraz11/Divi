# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""`avispria canopy`: the engine's surface model -> canopy height, cover, gaps and tree tops.

Reads ``odm_dem/dsm.tif`` (and ``odm_dem/dtm.tif`` when the engine made one) from a results
folder and writes ``canopy/``: ``chm.tif`` (canopy height in metres, float32, the DSM's
coordinate system), ``chm_preview.png`` (a quick look) and ``canopy_summary.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import Affine

from avispria.app.crowns_output import write_crowns
from avispria.app.ground_choice import choose_ground, onto
from avispria.app.paths import provenance_file
from avispria.core.canopy import (
    GREEN_THRESHOLD,
    CanopyStats,
    excess_green,
    extreme,
    summarize,
)
from avispria.core.crowns import CrownReport, analyse_crowns
from avispria.core.ground_sources import KIND_TEXT, GroundChoice, describe_choice

CANOPY_DIR = "canopy"
DEFAULT_CELL_M = 0.5  # fine enough for crowns, coarse enough to smooth photogrammetric noise
DEFAULT_EDGE_M = 5.0  # the outer rim of a surface model is seen by few photos: left out
DEFAULT_WINDOW_M = 80.0  # wider than the widest stand with no open ground in it


class CanopyError(RuntimeError):
    """The canopy model could not be made; the message says why."""


@dataclass(frozen=True)
class CanopyOutcome:
    stats: CanopyStats
    chm_path: Path
    preview_path: Path
    summary_path: Path
    crowns: CrownReport | None = None
    crowns_path: Path | None = None
    crowns_table: Path | None = None
    ground_choice: GroundChoice | None = None
    # the grids behind it, for the tree inventory: surface, ground used, ground seen
    grids: dict[str, np.ndarray] | None = None


def _read(path: Path, cell_m: float) -> tuple[np.ndarray, Affine, object]:
    with rasterio.open(path) as src:
        if src.crs is None or src.crs.is_geographic:
            raise CanopyError(f"{path.name} must be in metres (a projected coordinate system)")
        factor = max(1.0, cell_m / abs(src.res[0]))
        shape = (max(1, round(src.height / factor)), max(1, round(src.width / factor)))
        band = src.read(1, out_shape=shape, resampling=Resampling.average, masked=True)
        transform = src.transform * Affine.scale(src.width / shape[1], src.height / shape[0])
        return band.astype(float).filled(np.nan), transform, src.crs


_onto = onto  # used by the analysis engine too


def _colour(
    results_dir: Path, shape: tuple[int, int], transform: Affine, crs: object
) -> np.ndarray | None:
    """The orthophoto's colours on the canopy grid (rows x cols x 3), or None without one."""
    ortho = results_dir / "odm_orthophoto" / "odm_orthophoto.tif"
    if not ortho.is_file():
        return None
    bands = [_onto(ortho, shape, transform, crs, k, Resampling.average) for k in (1, 2, 3)]
    return np.stack(bands, axis=-1)


def _trim_edge(values: np.ndarray, cell_m: float, edge_m: float) -> np.ndarray:
    """Drop ``edge_m`` from the outer rim of the data (NaN treated as outside)."""
    radius = round(edge_m / cell_m)
    if radius <= 0:
        return values
    inside = extreme(np.where(np.isnan(values), 0.0, 1.0), radius, "min") > 0.5
    return np.where(inside, values, np.nan)


def _preview(chm: np.ndarray, path: Path, top_m: float) -> None:
    """Brown = open ground, greens = low to tall canopy, black = no data."""
    h = np.nan_to_num(chm, nan=-1.0)
    t = np.clip(h / max(top_m, 1.0), 0.0, 1.0)
    rgb = np.zeros((*h.shape, 3), dtype=np.uint8)
    rgb[..., 0] = np.where(h < 2.0, 150, (40 + 200 * t**2)).astype(np.uint8)
    rgb[..., 1] = np.where(h < 2.0, 120, (90 + 160 * t)).astype(np.uint8)
    rgb[..., 2] = np.where(h < 2.0, 80, 40).astype(np.uint8)
    rgb[h < 0] = 0
    Image.fromarray(rgb).save(path)


def run_canopy(
    results_dir: Path,
    *,
    cell_m: float = DEFAULT_CELL_M,
    window_m: float = DEFAULT_WINDOW_M,
    edge_m: float = DEFAULT_EDGE_M,
    sun_deg: float | None = None,
    crowns: bool = True,
    ground_file: Path | None = None,
    ground_kind: str = "lidar",
) -> CanopyOutcome:
    """Make the canopy products for an engine results folder."""
    dsm_path = results_dir / "odm_dem" / "dsm.tif"
    if not dsm_path.is_file():
        raise CanopyError(
            "no surface model (odm_dem/dsm.tif) in these results: process with the Standard or "
            "Detailed preset"
        )
    dsm, transform, crs = _read(dsm_path, cell_m)
    cell = abs(transform.a)
    dsm = _trim_edge(dsm, cell, edge_m)
    try:
        dtm, choice, seen = choose_ground(
            results_dir, dsm, transform, crs, window_m, ground_file, ground_kind
        )
    except (ValueError, OSError) as exc:
        raise CanopyError(str(exc)) from exc
    source = choice.kind
    try:
        rgb = _colour(results_dir, dsm.shape, transform, crs)
        green = None if rgb is None else excess_green(*np.moveaxis(rgb, -1, 0)) > GREEN_THRESHOLD
        chm, stats = summarize(dsm, dtm, cell, source, green)  # type: ignore[arg-type]
    except ValueError as exc:
        raise CanopyError(str(exc)) from exc
    out = results_dir / CANOPY_DIR
    out.mkdir(parents=True, exist_ok=True)
    chm_path = out / "chm.tif"
    profile = {
        "driver": "GTiff",
        "height": chm.shape[0],
        "width": chm.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": transform,
        "nodata": np.nan,
        "compress": "deflate",
    }
    with rasterio.open(chm_path, "w", **profile) as dst:
        dst.write(chm.astype(np.float32), 1)
    preview_path = out / "chm_preview.png"
    _preview(chm, preview_path, stats.height_p95_m)
    summary_path = out / "canopy_summary.json"
    record = asdict(stats) | {
        "ground_model": describe_choice(choice),
        "ground_choice": asdict(choice),
        "edge_trimmed_m": edge_m,
        "tree_height_threshold_m": 2.0,
        "green_index": f"excess green (2g-r-b)/(r+g+b) > {GREEN_THRESHOLD} (RGB proxy)",
    }
    if not crowns:  # the analysis engine makes them (run_analysis)
        summary_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        grids = {"dsm": dsm, "ground": dtm, "seen": seen}
        return CanopyOutcome(
            stats, chm_path, preview_path, summary_path, ground_choice=choice, grids=grids
        )
    sun_deg = recorded_sun(results_dir) if sun_deg is None else sun_deg
    report = analyse_crowns(chm, cell, None if rgb is None else np.nan_to_num(rgb), sun_deg)
    crowns_path, table_path = write_crowns(report, transform, crs, out)
    record |= {
        "sun_elevation_deg": sun_deg,
        "crowns": crowns_record(report),
    }
    summary_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return CanopyOutcome(
        stats,
        chm_path,
        preview_path,
        summary_path,
        report,
        crowns_path,
        table_path,
        choice,
        {"dsm": dsm, "ground": dtm, "seen": seen},
    )


def crowns_record(report: CrownReport) -> dict[str, object]:
    return {
        "trees": report.trees,
        "structures": report.structures,
        "dieback_candidates": report.dieback_candidates,
        "method": "tree tops (height-scaled window) + marker watershed; dieback = half the "
        "crown not green; flat not-green surfaces are structures",
        "issues": [asdict(i) for i in report.issues],
    }


def recorded_sun(results_dir: Path) -> float | None:
    """The sun elevation `process` recorded for these photos, if it did."""
    try:
        record = json.loads(provenance_file(results_dir.parent).read_text("utf-8"))
        value = (record.get("sun") or {}).get("elevation_deg")
    except (OSError, ValueError, AttributeError):
        return None
    return float(value) if isinstance(value, int | float) else None


def crowns_line(report: CrownReport) -> str:
    built = f", {report.structures} built structures left out" if report.structures else ""
    return (
        f"crowns: {report.trees} trees outlined{built}; {report.dieback_candidates} dieback "
        "candidate(s) to check on the ground (crowns.geojson opens in QGIS)"
    )


def describe(stats: CanopyStats) -> list[tuple[str, str]]:
    """The canopy numbers in plain words, for the CLI and the results screen."""
    ground = KIND_TEXT.get(stats.ground_source, stats.ground_source)
    return [
        ("canopy cover (trees 2 m and taller)", f"{stats.canopy_cover_pct:.0f}% of the area"),
        ("gaps and open ground", f"{stats.gap_pct:.0f}%"),
        (
            "canopy height",
            f"median {stats.height_p50_m:.1f} m, tallest 5% above {stats.height_p95_m:.1f} m",
        ),
        ("tree tops found", f"{stats.tree_tops} (about {stats.tree_tops_per_ha:.0f} per ha)"),
        ("ground", f"{ground}; seen directly in {stats.ground_seen_pct:.0f}% of the area"),
        (
            "tall but not green (roofs, vehicles, dry crowns)",
            f"{stats.tall_not_green_pct:.0f}% of the area, left out of the canopy figures",
        ),
    ]
