# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cut the stitched maps to an area ("extract by mask"), right after stitching.

The engine maps everything the photos saw, including the edges where few photos overlap and the
neighbours' land. Cutting to the study area (a KML, KMZ, shapefile, zipped shapefile or GeoJSON,
optionally widened by a buffer in metres) makes every later number (cover, trees, biomass per
hectare) about that area only.

The orthophoto, the surface model and the ground model are cut. Each original is kept beside it
as ``<name>.full.tif``, and cutting again (another shape, another buffer) always starts from the
original, so nothing is lost and a cut can be undone with ``restore_uncut``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import rasterio
from rasterio.errors import RasterioIOError
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_geom
from shapely.geometry import mapping
from shapely.geometry import shape as to_shape

from avispria.adapters.area_file import AreaFileError, area_from_file

PRODUCTS = (
    "odm_orthophoto/odm_orthophoto.tif",
    "odm_dem/dsm.tif",
    "odm_dem/dtm.tif",
)
FULL_SUFFIX = ".full.tif"


class ClipError(ValueError):
    """The maps could not be cut; the message says why."""


@dataclass(frozen=True)
class ClipOutcome:
    cut: list[Path]
    area_m2: float | None
    notes: list[str]


def _full(path: Path) -> Path:
    return path.with_name(path.name[: -len(".tif")] + FULL_SUFFIX)


def clip_results(results_dir: Path, mask_file: Path, buffer_m: float = 0.0) -> ClipOutcome:
    """Cut every product found in ``results_dir`` to the area in ``mask_file``."""
    try:
        area, found = area_from_file(mask_file, buffer_m)
    except AreaFileError as exc:
        raise ClipError(f"the area to cut by could not be used: {exc}") from None
    cut: list[Path] = []
    notes = list(found.notes)
    area_m2 = None
    for name in PRODUCTS:
        path = results_dir / name
        source = _full(path) if _full(path).is_file() else path
        if not source.is_file():
            continue
        try:
            src = rasterio.open(source)
        except RasterioIOError:
            notes.append(f"{name} could not be read, so it was not cut")
            continue
        with src:
            if src.crs is None:
                raise ClipError(f"{name} has no coordinate system: it cannot be cut")
            shape = transform_geom("EPSG:4326", src.crs, mapping(area))
            try:
                data, grid = rio_mask(src, [shape], crop=True, filled=True)
            except ValueError:
                raise ClipError(f"the area does not overlap {name}") from None
            profile = src.profile | {
                "height": data.shape[1],
                "width": data.shape[2],
                "transform": grid,
                "compress": "deflate",
            }
            if src.crs.is_projected and area_m2 is None:
                area_m2 = float(to_shape(shape).area)
        if source == path:
            path.replace(_full(path))  # keep the original
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data)
        cut.append(path)
    if not cut:
        raise ClipError("there are no maps to cut in these results")
    if buffer_m:
        notes.append(f"widened by {buffer_m:g} m")
    return ClipOutcome(cut, area_m2, notes)


def cut_step(
    results_dir: Path,
    mask_file: Path,
    buffer_m: float,
    step: Callable[[str], None],
    info: Callable[[str], None],
    warn: Callable[[str], None],
) -> ClipOutcome | None:
    """Extract by mask inside a processing job: a failure is said and the maps stay whole."""
    step("Cutting the maps to your area")
    try:
        cut = clip_results(results_dir, mask_file, buffer_m)
    except (ClipError, OSError) as exc:
        warn(f"the maps were not cut: {exc}")
        return None
    size = "" if cut.area_m2 is None else f" ({cut.area_m2 / 10_000:.2f} ha)"
    info(
        f"cut to {mask_file.name}{size}: {', '.join(p.name for p in cut.cut)}; the uncut "
        "originals are kept as *.full.tif"
    )
    return cut


def restore_uncut(results_dir: Path) -> list[Path]:
    """Put the originals back (undo a cut)."""
    restored = []
    for name in PRODUCTS:
        path = results_dir / name
        if _full(path).is_file():
            _full(path).replace(path)
            restored.append(path)
    return restored
