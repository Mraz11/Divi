# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crowns: synthetic domes of known size, a dead (brown) crown and a flat roof."""

import numpy as np
import pytest

from avispria.core.crowns import (
    analyse_crowns,
    local_spread,
    search_radius_cells,
    segment,
    srgb_to_lab,
)

CELL = 0.5


def stand() -> tuple[np.ndarray, np.ndarray, dict[str, tuple[int, int]]]:
    """Three round crowns (one dead, brown) and a flat 8 m roof, on open grass, 0.5 m cells."""
    rows, cols = np.mgrid[0:120, 0:120]
    chm = np.zeros((120, 120))
    rgb = np.zeros((120, 120, 3))
    rgb[:] = (90, 140, 60)  # grass
    trees = {"a": (30, 30, 18.0, 12), "b": (30, 85, 14.0, 10), "dead": (85, 30, 16.0, 11)}
    where = {}
    rng = np.random.default_rng(2)
    for name, (r, c, h, radius) in trees.items():
        d2 = (rows - r) ** 2 + (cols - c) ** 2
        inside = d2 <= radius**2
        leafy = h * np.sqrt(np.clip(1 - d2 / radius**2, 0, 1)) + rng.normal(0, 0.4, chm.shape)
        chm = np.where(inside, np.maximum(chm, leafy), chm)
        rgb[inside] = (130, 100, 70) if name == "dead" else (50, 120, 40)
        where[name] = (r, c)
    roof = (rows >= 70) & (rows < 100) & (cols >= 70) & (cols < 105)
    chm[roof] = 8.0
    rgb[roof] = (180, 180, 185)
    where["roof"] = (85, 87)
    return chm, rgb, where


def test_radius_grows_with_height() -> None:
    r = search_radius_cells(np.array([2.0, 20.0, 60.0]), CELL)
    assert list(r) == [3, 5, 8]


def test_three_trees_and_a_roof() -> None:
    chm, rgb, where = stand()
    labels = segment(chm, CELL)
    ids = {name: labels[rc] for name, rc in where.items()}
    assert len({ids["a"], ids["b"], ids["dead"]}) == 3 and 0 not in (ids["a"], ids["b"])
    report = analyse_crowns(chm, CELL, rgb, sun_elevation_deg=50.0)
    by_id = {c.id: c for c in report.crowns}
    a, dead, roof = by_id[ids["a"]], by_id[ids["dead"]], by_id[ids["roof"]]
    assert a.height_m == pytest.approx(18.0, abs=1.5)
    assert a.diameter_m == pytest.approx(12.0, abs=2.5)  # radius 12 cells = 6 m
    assert a.not_green == pytest.approx(0.0, abs=0.05) and not a.dieback
    assert dead.dieback and dead.redness is not None and dead.redness > a.redness  # type: ignore[operator]
    assert roof.structure and not roof.dieback
    assert report.trees == 3 and report.structures == 1 and report.dieback_candidates == 1
    assert report.issues == []


def test_low_sun_and_no_colour() -> None:
    chm, rgb, _ = stand()
    assert [i.code for i in analyse_crowns(chm, CELL, rgb, 5.0).issues] == ["CH003"]
    plain = analyse_crowns(chm, CELL)
    assert plain.dieback_candidates == 0 and all(c.not_green is None for c in plain.crowns)
    assert plain.structures == 1  # a flat roof is flat with or without colour


def test_helpers() -> None:
    lab = srgb_to_lab(np.array([[255.0, 255.0, 255.0], [0.0, 0.0, 0.0], [0.0, 128.0, 0.0]]))
    assert lab[0, 0] == pytest.approx(100, abs=0.1) and lab[1, 0] == pytest.approx(0, abs=0.1)
    assert lab[2, 1] < -40  # green is negative a*
    flat = local_spread(np.full((9, 9), 5.0), CELL)
    assert float(flat.max()) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        segment(np.zeros((3, 3)), 0.0)
    nothing = analyse_crowns(np.zeros((20, 20)), CELL)
    assert nothing.crowns == [] and nothing.trees == 0
