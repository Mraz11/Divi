# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cutting the stitched maps to an area (extract by mask)."""

from pathlib import Path

import pytest
import rasterio
from typer.testing import CliRunner

from avispria.app.cli import app
from avispria.app.clip_workflow import ClipError, clip_results, cut_step, restore_uncut
from forestscene import CELL, N, area_file, scene

runner = CliRunner()


def size(path: Path) -> tuple[int, int]:
    with rasterio.open(path) as src:
        return src.height, src.width


def near(got: tuple[int, int], want: tuple[int, int]) -> bool:
    """Within a few cells: the area's edges are curved lines on the map grid."""
    return all(abs(g - w) <= 3 for g, w in zip(got, want, strict=True))


def test_the_maps_are_cut_and_the_originals_kept(tmp_path: Path) -> None:
    root, _ = scene(tmp_path)
    mask = area_file(tmp_path, (20, 120), (40, 140), "kml")
    out = clip_results(root, mask)
    assert len(out.cut) == 3
    assert near(size(root / "odm_dem" / "dsm.tif"), (100, 100))
    assert size(root / "odm_dem" / "dsm.full.tif") == (N, N)
    assert out.area_m2 == pytest.approx(100 * 100 * CELL * CELL, rel=0.05)
    wider = clip_results(root, mask, buffer_m=5.0)  # cut again, from the original
    assert near(size(root / "odm_orthophoto" / "odm_orthophoto.tif"), (120, 120))
    assert "widened by 5 m" in wider.notes
    assert len(restore_uncut(root)) == 3
    assert size(root / "odm_dem" / "dsm.tif") == (N, N)


def test_cutting_problems_are_explained(tmp_path: Path) -> None:
    root, _ = scene(tmp_path)
    far = area_file(tmp_path, (5000, 5100), (5000, 5100), "geojson")
    with pytest.raises(ClipError, match="does not overlap"):
        clip_results(root, far)
    with pytest.raises(ClipError, match="could not be used"):
        clip_results(root, tmp_path / "missing.kml")
    with pytest.raises(ClipError, match="no maps to cut"):
        clip_results(tmp_path, area_file(tmp_path, (0, 10), (0, 10), "kml"))
    (root / "odm_orthophoto" / "odm_orthophoto.tif").write_bytes(b"not a raster")
    cut = clip_results(root, area_file(tmp_path, (20, 120), (40, 140), "kml"))
    assert len(cut.cut) == 2 and any("could not be read" in n for n in cut.notes)
    said: list[str] = []
    assert cut_step(root, far, 0.0, said.append, said.append, said.append) is None
    assert "not cut" in said[-1]
    assert cut_step(root, area_file(tmp_path, (20, 120), (40, 140), "kml"), 0, *[said.append] * 3)
    assert "originals are kept" in said[-1]


def test_the_clip_command(tmp_path: Path) -> None:
    root, _ = scene(tmp_path)
    mask = area_file(tmp_path, (20, 120), (40, 140), "kml")
    result = runner.invoke(app, ["clip", str(root), str(mask), "--buffer", "2"])
    assert result.exit_code == 0, result.output
    assert "ha; originals kept" in result.output
    assert runner.invoke(app, ["clip", str(root)]).exit_code == 2
    far = area_file(tmp_path, (5000, 5100), (5000, 5100), "geojson")
    assert runner.invoke(app, ["clip", str(root), str(far)]).exit_code == 1
    result = runner.invoke(app, ["clip", str(root), "--undo"])
    assert "put back: 3" in result.output
