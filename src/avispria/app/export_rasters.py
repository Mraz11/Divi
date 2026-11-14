# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One band, one file: Cloud-Optimised GeoTIFFs with a name, a unit and a QGIS style each.

A band is copied through a small in-memory VRT, so even a large orthophoto is streamed tile by
tile instead of read whole. The copy is a Cloud-Optimised GeoTIFF (tiled, compressed, with
overviews): it opens fast in QGIS at any zoom and is still an ordinary GeoTIFF for every other
program.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

import numpy as np
import rasterio
import rasterio.shutil
from rasterio._err import CPLE_BaseError
from rasterio.enums import Resampling
from rasterio.errors import RasterioError

from avispria.core.qml import RAMPS, pseudocolor

COG_OPTIONS = {
    "COMPRESS": "DEFLATE",
    "PREDICTOR": "YES",
    "BLOCKSIZE": "512",
    "OVERVIEWS": "AUTO",
    "BIGTIFF": "IF_SAFER",
}
SAMPLE_PX = 1024  # the longest side read to choose a colour stretch


class ExportError(ValueError):
    """A layer could not be exported; the message says why."""


@dataclass(frozen=True)
class BandSpec:
    source: Path
    band: int  # 1-based band of the source
    target: Path
    name: str  # what the band is, as QGIS and GDAL show it
    unit: str = ""
    ramp: str = "grey"  # a key of core.qml.RAMPS
    stretch: tuple[float, float] = (2.0, 98.0)  # percentiles for the colour ramp
    fixed: tuple[float, float] | None = None  # a fixed colour range instead (e.g. 0..255)
    mask_band: int | None = None  # the source band that says which pixels are valid (alpha)


DTYPES = {
    "uint8": "Byte",
    "uint16": "UInt16",
    "int16": "Int16",
    "uint32": "UInt32",
    "int32": "Int32",
    "float32": "Float32",
    "float64": "Float64",
}


def band_vrt(spec: BandSpec) -> str:
    """A VRT holding one band of the source, with its name, unit, no-data and mask."""
    with rasterio.open(spec.source) as src:
        if not 1 <= spec.band <= src.count:
            raise ExportError(f"{spec.source.name} has no band {spec.band}")
        dtype = DTYPES.get(src.dtypes[spec.band - 1])
        if dtype is None:
            raise ExportError(f"{spec.source.name}: data type {src.dtypes[spec.band - 1]}")
        nodata = src.nodatavals[spec.band - 1]
        mask_band = spec.mask_band if spec.mask_band and spec.mask_band <= src.count else None
        width, height, crs, gt = src.width, src.height, src.crs, src.transform.to_gdal()
    source = escape(str(spec.source.resolve()))

    def simple(band: int) -> str:
        return (
            f'<SimpleSource><SourceFilename relativeToVRT="0">{source}</SourceFilename>'
            f"<SourceBand>{band}</SourceBand></SimpleSource>"
        )

    mask = ""
    if mask_band is not None:  # an alpha band: 0 is outside the map
        alpha = simple(mask_band)
        mask = f'<MaskBand><VRTRasterBand dataType="Byte">{alpha}</VRTRasterBand></MaskBand>'
    nd = "" if nodata is None else f"<NoDataValue>{nodata!r}</NoDataValue>"
    unit = f"<UnitType>{escape(spec.unit)}</UnitType>" if spec.unit else ""
    return (
        f'<VRTDataset rasterXSize="{width}" rasterYSize="{height}">'
        f"<SRS>{escape(crs.to_wkt()) if crs else ''}</SRS>"
        f"<GeoTransform>{', '.join(repr(v) for v in gt)}</GeoTransform>"
        f'<VRTRasterBand dataType="{dtype}" band="1">'
        f"<Description>{escape(spec.name)}</Description>{nd}{unit}{simple(spec.band)}"
        f"</VRTRasterBand>{mask}</VRTDataset>"
    )


def colour_range(spec: BandSpec) -> tuple[float, float]:
    """The values the colour ramp spans: fixed, or percentiles of a small sample."""
    if spec.fixed is not None:
        return spec.fixed
    with rasterio.open(spec.source) as src:
        scale = max(1.0, max(src.width, src.height) / SAMPLE_PX)
        shape = (max(1, round(src.height / scale)), max(1, round(src.width / scale)))
        values = src.read(
            spec.band, out_shape=shape, resampling=Resampling.nearest, masked=True
        ).astype(float)
    found = values.compressed() if np.ma.isMaskedArray(values) else values.ravel()
    found = found[np.isfinite(found)]
    if found.size == 0:
        return 0.0, 1.0
    low, high = np.percentile(found, list(spec.stretch))
    return float(low), float(max(high, low + 1e-6))


def export_band(spec: BandSpec) -> Path:
    """Write the band as a Cloud-Optimised GeoTIFF with a QGIS style beside it."""
    spec.target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with rasterio.open(band_vrt(spec)) as vrt:
            rasterio.shutil.copy(vrt, spec.target, driver="COG", **COG_OPTIONS)
        low, high = colour_range(spec)
    except (RasterioError, CPLE_BaseError) as exc:
        raise ExportError(f"{spec.target.name} could not be written: {exc}") from None
    style = pseudocolor(low, high, RAMPS[spec.ramp], spec.unit)
    spec.target.with_suffix(".qml").write_text(style, encoding="utf-8")
    return spec.target


def export_whole(source: Path, target: Path) -> Path:
    """Copy a raster as it is (all bands, colour table) to a Cloud-Optimised GeoTIFF."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with rasterio.open(source) as src:
            rasterio.shutil.copy(src, target, driver="COG", **COG_OPTIONS)
    except (RasterioError, CPLE_BaseError) as exc:
        raise ExportError(f"{target.name} could not be written: {exc}") from None
    return target
