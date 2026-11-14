# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DeepForest as an optional second pass on the crowns (the detector itself is faked)."""

import json
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage as ndi

from avispria.adapters import tree_detector
from avispria.adapters.tree_detector import TreeBox, TreeDetectorError
from avispria.app.crown_boxes import boxes_for
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.surface_workflow import run_analysis
from avispria.core.crowns import refine_tops, tree_tops
from forestscene import GRID, TREES, scene


def test_boxes_add_a_missed_tree_and_merge_a_split_one() -> None:
    smooth = np.zeros((60, 60))
    smooth[5:25, 5:25] = 12.0  # a flat-topped crown: no single top
    smooth[10, 10] = 13.0
    smooth[10, 18] = 13.0  # the height model sees two tops in one crown
    smooth[40:55, 40:55] = 9.0
    markers = tree_tops(smooth, 0.5)
    markers[40:55, 40:55] = 0  # a tree the height model missed
    before = len(np.unique(markers[markers > 0]))
    out, added, merged = refine_tops(
        markers, smooth, [(4, 4, 26, 26), (38, 38, 57, 57), (0, 0, 1, 1)]
    )
    assert added == 1 and merged >= 1
    assert len(np.unique(out[out > 0])) == before - merged + added
    assert out[40:55, 40:55].max() > 0
    _, n = ndi.label(out[5:25, 5:25] > 0)
    assert len(np.unique(out[5:25, 5:25][out[5:25, 5:25] > 0])) == 1 and n >= 1


def test_without_deepforest_the_crowns_stay_and_the_reason_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = scene(tmp_path)
    monkeypatch.setattr(tree_detector, "available", lambda: False)
    with pytest.raises(TreeDetectorError, match="uv sync --extra trees"):
        tree_detector.detect(root / "odm_orthophoto" / "odm_orthophoto.tif")
    outcome = run_analysis(root, "forest", trees=TreeInputs(deepforest=True))
    summary = json.loads(outcome.summary_path.read_text("utf-8"))
    assert summary["crown_detector"].startswith("DeepForest not used: DeepForest is not installed")
    assert outcome.result.crowns.trees == len(TREES)


def test_detector_boxes_reach_the_crowns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = scene(tmp_path)
    found = []
    for r, c, _h in TREES:
        x0, y1 = GRID * (c - 10, r - 10)
        x1, y0 = GRID * (c + 10, r + 10)
        found.append(TreeBox(x0, y0, x1, y1, 0.9))
    monkeypatch.setattr(tree_detector, "detect", lambda ortho: found)
    boxes, note = boxes_for(root, GRID, (200, 200))
    assert len(boxes) == len(TREES) and "found 9 trees" in note
    r, c, _ = TREES[0]
    assert boxes[0] == (r - 10, c - 10, r + 10, c + 10)
    outcome = run_analysis(root, "forest", trees=TreeInputs(deepforest=True))
    summary = json.loads(outcome.summary_path.read_text("utf-8"))
    assert "corrected the tree tops" in summary["crown_detector"]
    assert outcome.result.crowns.trees == len(TREES)
    assert boxes_for(tmp_path, GRID, (10, 10))[1] == "DeepForest not used: no orthophoto"


def test_a_failing_model_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = scene(tmp_path)

    class Broken:
        def predict_tile(self, path: str, patch_size: int, patch_overlap: float) -> None:
            raise RuntimeError("no weights")

    monkeypatch.setattr(tree_detector, "available", lambda: True)
    monkeypatch.setattr(tree_detector, "_model", lambda: Broken())
    with pytest.raises(TreeDetectorError, match="DeepForest failed: no weights"):
        tree_detector.detect(root / "odm_orthophoto" / "odm_orthophoto.tif")

    class Empty:
        def predict_tile(self, raster_path: str, patch_size: int, patch_overlap: float) -> list:  # type: ignore[type-arg]
            assert Path(raster_path).name == "ortho_10cm.tif"
            return []

    monkeypatch.setattr(tree_detector, "_model", lambda: Empty())
    assert tree_detector.detect(root / "odm_orthophoto" / "odm_orthophoto.tif") == []
