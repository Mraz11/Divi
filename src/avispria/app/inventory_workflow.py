# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The tree inventory: checked heights, crowns, biomass and carbon with ranges, visible
symptoms, and colour indices. Runs after the analysis engine, on its crowns.

Writes into ``results/analysis/``:
* ``trees.csv``: every tree: position, height (as modelled, and corrected with field trees),
  crown size, biomass and CO2 with their 95 % ranges, colour scores and symptom flags
* ``inventory_summary.json``: the quality grade and its findings, the ground model used, the
  doming check, the height correction, the stand's totals with ranges, every assumption
* ``ground_sigma.tif``: the ground's uncertainty at each place (m)
* ``indices/``: colour indices (relative within this flight), the vegetation mask

Inputs that make it better (all optional, ``TreeInputs``): an outside ground model, an
independent ground model to check doming, field-measured tree heights (CSV), the wood density of
the forest type, the carbon fraction, conifers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.transform import Affine

from avispria.app.ground_choice import onto
from avispria.app.inventory_files import (
    InventoryError,
    read_field_heights,
    write_raster,
    write_trees,
)
from avispria.core.analyses import checked, on
from avispria.core.biomass import BiomassInputs, StandBiomass, stand_biomass
from avispria.core.chm_quality import ChmQuality, check_chm
from avispria.core.crowns import LOW_SUN_DEG, CrownReport
from avispria.core.doming import DomeCheck, check_doming, not_checked
from avispria.core.ground_sources import (
    BASE_SIGMA_M,
    GROWTH_M_PER_M,
    OUTSIDE_KINDS,
    GroundChoice,
    align,
    distance_to_seen,
    ground_sigma,
)
from avispria.core.height_calibration import NONE, HeightCalibration, calibrate
from avispria.core.indices import CAVEAT, INDICES, flight_summary, rank_change, vegetation_mask
from avispria.core.symptoms import SymptomReport, crown_symptoms

APEX_SD_M = 0.7  # crown tops smoothed away: -0.5 to -0.8 m (Young et al. 2021), as uncertainty


@dataclass(frozen=True)
class TreeInputs:
    ground_file: Path | None = None
    ground_kind: str = "lidar"  # lidar, leaf-off, survey or global
    reference_file: Path | None = None  # an independent ground model for the doming check
    field_heights: Path | None = None  # CSV: lat, lon (or x, y), height_m; id optional
    deepforest: bool = False  # correct the crowns with DeepForest's tree boxes (optional extra)
    biomass: BiomassInputs = field(default_factory=BiomassInputs)
    off: tuple[str, ...] = ()  # analyses switched off (core/analyses.py)

    def record(self) -> dict[str, Any]:
        out = asdict(self)
        for k in ("ground_file", "reference_file", "field_heights"):
            out[k] = None if out[k] is None else str(out[k])
        return out

    @classmethod
    def from_record(cls, raw: dict[str, Any] | None) -> TreeInputs:
        if not raw:
            return cls()
        paths = {
            k: (Path(raw[k]) if raw.get(k) else None)
            for k in ("ground_file", "reference_file", "field_heights")
        }
        return cls(
            ground_kind=str(raw.get("ground_kind", "lidar")),
            deepforest=bool(raw.get("deepforest", False)),
            biomass=BiomassInputs(**(raw.get("biomass") or {})),
            off=checked(raw.get("off") or ()),
            **paths,
        )


@dataclass(frozen=True)
class InventoryOutcome:
    quality: ChmQuality
    calibration: HeightCalibration
    biomass: StandBiomass | None  # None: switched off
    symptoms: SymptomReport | None
    trees_path: Path
    summary_path: Path
    area_ha: float


def _indices(rgb: np.ndarray, out: Path, grid: Affine, crs: object) -> dict[str, Any]:
    folder = out / "indices"
    summary: dict[str, Any] = {"caveat": CAVEAT, "indices": {}}
    for name, (fn, text) in INDICES.items():
        values = fn(rgb)
        write_raster(folder / f"{name}.tif", values, grid, crs)
        summary["indices"][name] = {"what": text, "this_flight": flight_summary(values)}
    mask, rule = vegetation_mask(rgb)
    write_raster(folder / "vegetation_mask.tif", mask.astype(float), grid, crs)
    summary["vegetation_mask"] = {"rule": rule, "share_pct": round(float(mask.mean()) * 100, 1)}
    return summary


def _doming(
    inputs: TreeInputs, dsm: np.ndarray, seen: np.ndarray, grid: Affine, crs: object
) -> DomeCheck:
    """This flight's surface where it saw the ground, against an independent ground model."""
    if inputs.reference_file is None:
        return not_checked()
    if inputs.ground_file is not None and inputs.reference_file == inputs.ground_file:
        raise InventoryError("the doming check needs a model other than the ground model used")
    ref = onto(inputs.reference_file, dsm.shape, grid, crs)
    ref, _, _ = align(ref, dsm, seen)
    return check_doming(dsm, ref, seen, abs(grid.a))


def run_inventory(
    results_dir: Path,
    grids: dict[str, np.ndarray],
    choice: GroundChoice,
    crowns: CrownReport,
    rgb: np.ndarray | None,
    grid: Affine,
    crs: object,
    sun_deg: float | None,
    inputs: TreeInputs,
) -> InventoryOutcome:
    out = results_dir / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    cell = abs(grid.a)
    dsm, ground, seen = grids["dsm"], grids["ground"], grids["seen"]
    sigma = ground_sigma(choice.kind, distance_to_seen(seen, cell))
    write_raster(out / "ground_sigma.tif", np.where(np.isfinite(dsm), sigma, np.nan), grid, crs)
    trees = [c for c in crowns.crowns if not c.structure]
    rows = np.array([int(c.row) for c in trees], dtype=int)
    cols = np.array([int(c.col) for c in trees], dtype=int)
    xs, ys = grid * (cols + 0.5, rows + 0.5) if trees else (np.array([]), np.array([]))
    heights = np.array([c.height_m for c in trees], dtype=float)
    field_trees = (
        read_field_heights(inputs.field_heights, crs) if inputs.field_heights is not None else []
    )
    calibration = (
        calibrate(np.column_stack([xs, ys]) if trees else np.zeros((0, 2)), heights, field_trees)
        if field_trees
        else NONE
    )
    corrected = calibration.apply(heights)
    at_tops = sigma[rows, cols] if trees else np.array([])
    doming = _doming(inputs, dsm, seen, grid, crs)
    quality = check_chm(
        dsm,
        ground,
        np.isfinite(dsm),
        choice.seen_pct,
        at_tops,
        doming,
        choice.kind in OUTSIDE_KINDS,
    )
    if calibration.residual_sd_m is not None:
        own = np.full(len(trees), calibration.residual_sd_m)
        shared = calibration.residual_sd_m / np.sqrt(max(1, calibration.matched))
    else:
        own, shared = at_tops, APEX_SD_M
    diameters = np.array([c.diameter_m for c in trees], dtype=float)
    stand = (
        stand_biomass(
            corrected, diameters, own, replace(inputs.biomass, shared_height_sd_m=float(shared))
        )
        if on("biomass", inputs.off)
        else None
    )
    symptoms = None
    if rgb is not None and trees and on("symptoms", inputs.off):
        low = sun_deg is not None and sun_deg < LOW_SUN_DEG
        symptoms = crown_symptoms(
            crowns.labels, rgb, [c.id for c in trees], {c.id for c in trees if c.dieback}, cell, low
        )
    area_ha = float(np.isfinite(dsm).sum()) * cell * cell / 10_000
    trees_path = write_trees(out, trees, xs, ys, crs, heights, corrected, stand, symptoms)
    record = {
        "quality": asdict(quality),
        "ground_choice": asdict(choice),
        "height_calibration": asdict(calibration),
        "biomass": None if stand is None else _biomass_record(stand, area_ha, inputs),
        "symptoms": None
        if symptoms is None
        else {
            "candidates": symptoms.candidates,
            "candidate_crown_area_pct": symptoms.candidate_area_pct,
            "notes": symptoms.notes,
        },
        "indices": None
        if rgb is None or not on("indices", inputs.off)
        else _indices(rgb, out, grid, crs),
        "assumptions": {
            "ground_sigma_m": BASE_SIGMA_M,
            "ground_sigma_growth_m_per_m": GROWTH_M_PER_M,
            "crown_top_smoothing_sd_m": APEX_SD_M,
            "inputs": inputs.record(),
        },
        "area_ha": round(area_ha, 4),
    }
    summary_path = out / "inventory_summary.json"
    summary_path.write_text(json.dumps(record, indent=2, default=_plain), encoding="utf-8")
    return InventoryOutcome(
        quality, calibration, stand, symptoms, trees_path, summary_path, area_ha
    )


def write_rank_change(before: Path, after: Path, out: Path) -> Path:
    """The later flight's index ranked within its flight, minus the earlier one's, on the
    earlier flight's grid."""
    with rasterio.open(before) as src:
        first = src.read(1).astype(float)
        grid, crs = src.transform, src.crs
        nodata = src.nodata
    if nodata is not None:
        first[first == nodata] = np.nan
    second = onto(after, first.shape, grid, crs)
    write_raster(out, rank_change(first, second), grid, crs)
    return out


def describe_inventory(inv: InventoryOutcome) -> list[tuple[str, str]]:
    """The inventory in plain words (CLI, job log, results screen)."""
    q, b = inv.quality, inv.biomass
    rows = [("canopy height model", f"{q.grade}" + (f": {q.findings[0]}" if q.findings else ""))]
    rows += [("", f) for f in q.findings[1:]]
    rows.append(("doming", q.doming.note))
    rows.append(("height correction", inv.calibration.note))
    if b is not None and b.trees:
        per_ha = 1000 * inv.area_ha if inv.area_ha > 0 else float("nan")
        rows.append(
            (
                "biomass (above ground)",
                f"{b.agb_kg.median / 1000:.1f} t (95 % range {b.agb_kg.low / 1000:.1f} to "
                f"{b.agb_kg.high / 1000:.1f} t), {b.agb_kg.median / per_ha:.1f} t per ha, "
                f"{len(b.trees)} trees",
            )
        )
        rows.append(
            (
                "CO2 equivalent",
                f"{b.co2e_kg.median / 1000:.1f} t ({b.co2e_kg.low / 1000:.1f} to "
                f"{b.co2e_kg.high / 1000:.1f} t); one tree alone is uncertain about "
                f"{b.band_one_tree:.1f} times either way",
            )
        )
    if inv.symptoms is not None:
        s = inv.symptoms
        rows.append(
            (
                "visible symptoms",
                f"{s.candidates} crown(s) to check on the ground ({s.candidate_area_pct:.0f}% "
                "of the crown area); visible symptoms only, not latent infection",
            )
        )
    return rows


def _plain(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON: {type(value).__name__}")


def _biomass_record(stand: StandBiomass, area_ha: float, inputs: TreeInputs) -> dict[str, Any]:
    per_ha = 1 / area_ha if area_ha > 0 else float("nan")
    return {
        "trees": len(stand.trees),
        "agb_kg_jucker": asdict(stand.agb_kg),
        "agb_kg_chave": asdict(stand.agb_chave_kg),
        "carbon_kg": asdict(stand.carbon_kg),
        "co2e_kg": asdict(stand.co2e_kg),
        "agb_t_per_ha_jucker": {
            k: round(v / 1000 * per_ha, 2) for k, v in asdict(stand.agb_kg).items()
        },
        "one_tree_band": stand.band_one_tree,
        "draws": stand.draws,
        "method": "Jucker et al. 2017 Eq. 7 (main); Chave et al. 2014 Eq. 4 with D from Jucker "
        "Eq. 6 (second opinion); Monte Carlo of height, crown, wood density, carbon fraction and "
        "equation scatter; ranges are 2.5 to 97.5 %",
        "limits": "an estimate assisted by remote sensing (IPCC Tier 1 defaults), not a carbon "
        "credit; plantation and agroforestry trees were not in Jucker's data; urban, open-grown "
        "trees differ from forest trees; local allometry and field plots are needed for more",
        "wood_density": inputs.biomass.wood_density,
        "carbon_fraction": inputs.biomass.carbon_fraction,
    }
