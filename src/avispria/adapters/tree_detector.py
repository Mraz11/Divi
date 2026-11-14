# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DeepForest, a pretrained tree-crown detector (Weinstein et al. 2020; MIT licence), as an
optional second opinion on the crowns.

It is not installed with Dīvi: it brings PyTorch (about 1 to 2 GB) and downloads its model
(about 100 MB) the first time. Install it with ``uv sync --extra trees``. Without it, the crowns
come from the canopy height model alone, as before.

The model was trained on RGB photos at about 10 cm per pixel, so the orthophoto is resampled to
10 cm before detection. It finds one class, "Tree", as boxes; its authors note that town and
coarse images can work but need extra effort (fine-tuning), so its boxes are used only to
correct the height-model crowns (see core/crowns.py), never on their own.
"""

from __future__ import annotations

import importlib.util
import inspect
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine

MODEL_CM = 10.0
MIN_SCORE = 0.3
MODEL_NAME = "weecology/deepforest-tree"
INSTALL = "uv sync --extra trees"


class TreeDetectorError(RuntimeError):
    """DeepForest could not run; the message says why (and how to install it)."""


@dataclass(frozen=True)
class TreeBox:
    """A detected crown, in the orthophoto's map coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float
    score: float


def available() -> bool:
    return importlib.util.find_spec("deepforest") is not None


def _to_model_scale(ortho: Path, folder: Path) -> tuple[Path, Affine]:
    """The orthophoto's colours at about 10 cm per pixel (finer photos are averaged down)."""
    with rasterio.open(ortho) as src:
        if src.count < 3:
            raise TreeDetectorError(f"{ortho.name} has no colour bands")
        cell_cm = abs(src.res[0]) * 100 if src.crs and src.crs.is_projected else MODEL_CM
        factor = max(1.0, MODEL_CM / cell_cm)
        shape = (max(1, round(src.height / factor)), max(1, round(src.width / factor)))
        data = src.read((1, 2, 3), out_shape=(3, *shape), resampling=Resampling.average)
        grid = src.transform * Affine.scale(src.width / shape[1], src.height / shape[0])
        profile = {
            "driver": "GTiff", "height": shape[0], "width": shape[1], "count": 3,
            "dtype": "uint8", "crs": src.crs, "transform": grid,
        }  # fmt: skip
    path = folder / "ortho_10cm.tif"
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.clip(data, 0, 255).astype(np.uint8))
    return path, grid


def _model() -> Any:
    from deepforest import main  # optional dependency

    model = main.deepforest()
    loader = getattr(model, "load_model", None)
    if loader is not None:
        try:
            loader(model_name=MODEL_NAME)
            return model
        except TypeError:
            pass
    model.use_release()  # DeepForest 1.x
    return model


def _predict(model: Any, path: Path) -> Any:
    params = inspect.signature(model.predict_tile).parameters
    key = "path" if "path" in params else "raster_path"
    return model.predict_tile(**{key: str(path)}, patch_size=400, patch_overlap=0.25)


def detect(ortho: Path) -> list[TreeBox]:
    """Tree boxes on the orthophoto, in its map coordinates."""
    if not available():
        raise TreeDetectorError(f"DeepForest is not installed; install it with: {INSTALL}")
    with tempfile.TemporaryDirectory() as tmp:
        path, grid = _to_model_scale(ortho, Path(tmp))
        try:
            found = _predict(_model(), path)
        except Exception as exc:  # a third-party model: any failure is reported, not raised
            raise TreeDetectorError(f"DeepForest failed: {exc}") from exc
    if found is None or len(found) == 0:
        return []
    boxes = []
    for row in found.itertuples():
        score = float(getattr(row, "score", 1.0))
        if score < MIN_SCORE:
            continue
        x0, y0 = grid * (float(row.xmin), float(row.ymin))
        x1, y1 = grid * (float(row.xmax), float(row.ymax))
        boxes.append(TreeBox(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), score))
    return boxes
