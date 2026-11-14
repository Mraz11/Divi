# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DeepForest's tree boxes on the analysis grid, to correct the height-model crowns.

Optional: without DeepForest installed, or when it fails, the crowns come from the canopy height
model alone and the reason is recorded; the analysis never stops because of it.
"""

from __future__ import annotations

from pathlib import Path

from rasterio.transform import Affine

from avispria.adapters import tree_detector

Box = tuple[int, int, int, int]


def boxes_for(results_dir: Path, grid: Affine, shape: tuple[int, int]) -> tuple[list[Box], str]:
    """The detector's boxes as grid cells (r0, c0, r1, c1), and a line saying what happened."""
    ortho = results_dir / "odm_orthophoto" / "odm_orthophoto.tif"
    if not ortho.is_file():
        return [], "DeepForest not used: no orthophoto"
    try:
        found = tree_detector.detect(ortho)
    except tree_detector.TreeDetectorError as exc:
        return [], f"DeepForest not used: {exc}"
    inverse = ~grid
    boxes: list[Box] = []
    h, w = shape
    for b in found:
        c0, r0 = inverse * (b.x0, b.y1)  # top left: smaller row at the larger y
        c1, r1 = inverse * (b.x1, b.y0)
        r0, c0 = max(0, int(r0)), max(0, int(c0))
        r1, c1 = min(h, round(r1)), min(w, round(c1))
        if r1 > r0 and c1 > c0:
            boxes.append((r0, c0, r1, c1))
    return boxes, f"DeepForest found {len(found)} trees; its boxes corrected the tree tops"
