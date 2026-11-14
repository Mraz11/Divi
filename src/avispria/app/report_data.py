# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the report is made of: the records the engines left in the maps folder, and pictures.

Every file is optional: a project that was only planned still gets a report, with what there is.
A file that cannot be read is named in ``missing`` instead of stopping the report.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.errors import RasterioError

from avispria.app.engines import ORTHO, EngineState, Links, inspect
from avispria.app.paths import provenance_file

CANOPY = "canopy/canopy_summary.json"
SURFACE = "analysis/surface_summary.json"
INVENTORY = "analysis/inventory_summary.json"
PICTURES = (
    ("Orthophoto", ORTHO),
    (
        "Canopy height model: brown is open ground; green from dark (low) to light (the 95th "
        "percentile height and above); black is no data",
        "canopy/chm_preview.png",
    ),
    ("Land cover", "analysis/landcover_preview.png"),
)
LONGEST_PX = 1400  # a picture's longest side in the report


@dataclass
class ReportData:
    name: str
    states: tuple[EngineState, ...]
    stamps: dict[str, dict[str, str]]
    links: Links
    provenance: dict[str, Any] | None = None
    canopy: dict[str, Any] | None = None
    surface: dict[str, Any] | None = None
    inventory: dict[str, Any] | None = None
    pictures: list[tuple[str, bytes]] = field(default_factory=list)  # (caption, PNG)
    missing: list[str] = field(default_factory=list)  # files there but unreadable


def read_json(path: Path, missing: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        missing.append(path.name)
        return None
    if not isinstance(found, Mapping):
        missing.append(path.name)
        return None
    return dict(found)


def _png(image: Image.Image) -> bytes:
    image.thumbnail((LONGEST_PX, LONGEST_PX))
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def ortho_picture(path: Path) -> bytes:
    """A small colour picture of an orthophoto, read at reduced size (never the whole raster)."""
    with rasterio.open(path) as src:
        scale = max(src.width, src.height) / LONGEST_PX
        shape = (
            max(1, round(src.height / max(scale, 1))),
            max(1, round(src.width / max(scale, 1))),
        )
        bands = [1, 2, 3] if src.count >= 3 else [1, 1, 1]
        rgb = src.read(bands, out_shape=(3, *shape), resampling=Resampling.average)
        alpha = (
            src.read(4, out_shape=shape, resampling=Resampling.nearest)
            if src.count >= 4
            else np.full(shape, 255)
        )
    if rgb.dtype != np.uint8:  # 16-bit or float: stretch to the 2nd-98th percentile
        seen = rgb[:, alpha > 0] if (alpha > 0).any() else rgb.reshape(3, -1)
        low, high = np.percentile(seen, [2, 98]) if seen.size else (0, 1)
        rgb = np.clip((rgb - low) / max(float(high - low), 1e-9) * 255, 0, 255)
    pixels = np.dstack([*rgb.astype(np.uint8), alpha.astype(np.uint8)])
    return _png(Image.fromarray(pixels, "RGBA"))


def picture(path: Path) -> bytes:
    if path.suffix.lower() == ".tif":
        return ortho_picture(path)
    with Image.open(path) as found:
        return _png(found.convert("RGBA"))


def gather(
    links: Links, name: str = "", stamps: dict[str, dict[str, str]] | None = None
) -> ReportData:
    states = tuple(
        replace(s, status="done", detail="This report") if s.spec.key == "report" else s
        for s in inspect(links)
    )
    data = ReportData(name, states, dict(stamps or {}), links)
    results = links.results
    if results is None:
        return data
    data.provenance = read_json(provenance_file(Path(links.maps_folder)), data.missing)
    data.canopy = read_json(results / CANOPY, data.missing)
    data.surface = read_json(results / SURFACE, data.missing)
    data.inventory = read_json(results / INVENTORY, data.missing)
    for caption, relative in PICTURES:
        path = results / relative
        if not path.is_file():
            continue
        try:
            data.pictures.append((caption, picture(path)))
        except (OSError, ValueError, RasterioError):
            data.missing.append(path.name)
    return data
