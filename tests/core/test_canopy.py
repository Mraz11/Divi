# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canopy height: a synthetic forest on a sloping field, with known tree heights."""

import numpy as np
import pytest

from avispria.core.canopy import (
    box_mean,
    canopy_height,
    estimate_ground,
    extreme,
    fill_from,
    ground_cells,
    summarize,
    tree_tops,
)

CELL = 0.5


def forest(
    size: int = 240, slope: float = 0.02, crowns: int = 30, seed: int = 4
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int, float]]]:
    """A gently sloping ground with round crowns of known height (metres, 0.5 m cells)."""
    rng = np.random.default_rng(seed)
    rows, cols = np.mgrid[0:size, 0:size]
    ground = 50.0 + slope * cols * CELL
    dsm = ground.copy()
    trees = []
    for _ in range(crowns):
        r, c = rng.integers(40, size - 40, 2)
        h = float(rng.uniform(8, 24))
        radius = float(rng.uniform(4, 9)) / CELL
        d2 = (rows - r) ** 2 + (cols - c) ** 2
        dome = ground + h * np.sqrt(np.clip(1 - d2 / radius**2, 0, 1))
        dsm = np.maximum(dsm, np.where(d2 <= radius**2, dome, -np.inf))
        trees.append((int(r), int(c), h))
    return dsm, ground, trees


def test_extreme_ignores_nan() -> None:
    a = np.array([[1.0, np.nan, 3.0], [4.0, 5.0, 6.0]])
    assert extreme(a, 1, "min")[0, 1] == 1.0
    assert extreme(a, 1, "max")[1, 0] == 5.0
    assert np.isnan(extreme(np.full((2, 2), np.nan), 1, "max")).all()


def test_box_mean_keeps_nan_and_averages() -> None:
    a = np.array([[1.0, 2.0, 3.0], [4.0, np.nan, 6.0]])
    out = box_mean(a, 1)
    assert np.isnan(out[1, 1])
    assert out[0, 0] == pytest.approx((1 + 2 + 4) / 3)
    assert box_mean(a, 0) is not a


def test_fill_from_reaches_every_cell() -> None:
    a = np.arange(25, dtype=float).reshape(5, 5)
    valid = np.zeros((5, 5), dtype=bool)
    valid[0, 0] = valid[4, 4] = True
    out = fill_from(a, valid)
    assert not np.isnan(out).any()
    assert out[0, 0] == 0.0 and out[4, 4] == 24.0


def test_ground_cells_reject_crowns_keep_open_ground() -> None:
    dsm, ground, _ = forest()
    keep = ground_cells(dsm, CELL, max_window_m=40)
    crown = dsm - ground > 3
    assert keep[crown].mean() < 0.02
    assert keep[~crown].mean() > 0.6


def test_estimated_ground_recovers_the_slope() -> None:
    dsm, ground, _ = forest()
    est = estimate_ground(dsm, CELL, max_window_m=40)
    assert np.nanmax(np.abs(est - ground)) < 1.5
    assert np.nanmedian(np.abs(est - ground)) < 0.2


def test_canopy_height_and_tops_match_the_trees() -> None:
    dsm, ground, trees = forest()
    chm = canopy_height(dsm, ground)
    assert chm.min() == 0.0
    tallest = max(h for _, _, h in trees)
    assert np.max(chm) == pytest.approx(tallest, abs=0.05)
    # overlapping crowns merge, so the count is at most the number of trees and not far below it
    assert 0.6 * len(trees) <= tree_tops(chm, CELL) <= len(trees)


def test_summary_numbers_and_warnings() -> None:
    dsm, ground, _ = forest()
    chm, stats = summarize(dsm, ground, CELL, "engine")
    canopy = chm >= 2.0
    assert stats.canopy_cover_pct == pytest.approx(canopy.mean() * 100, abs=0.1)
    assert stats.gap_pct == pytest.approx(100 - stats.canopy_cover_pct, abs=0.11)
    assert stats.area_m2 == pytest.approx(240 * 240 * CELL * CELL)
    assert stats.height_p95_m <= stats.height_max_m
    assert stats.issues == []  # plenty of open ground, engine ground model
    _, est = summarize(dsm, estimate_ground(dsm, CELL, 40), CELL, "estimated")
    assert [i.code for i in est.issues] == ["CH002"]


def test_closed_canopy_warns_that_the_ground_is_guessed() -> None:
    dsm = np.full((50, 50), 70.0)
    ground = np.full((50, 50), 50.0)
    _, stats = summarize(dsm, ground, 1.0, "engine")
    assert [i.code for i in stats.issues] == ["CH001"]
    assert stats.canopy_cover_pct == 100.0


def test_bad_inputs() -> None:
    with pytest.raises(ValueError):
        canopy_height(np.zeros((2, 2)), np.zeros((3, 3)))
    with pytest.raises(ValueError):
        summarize(np.full((2, 2), np.nan), np.zeros((2, 2)), 1.0, "engine")
    with pytest.raises(ValueError):
        ground_cells(np.zeros((2, 2)), 0.0)
    with pytest.raises(ValueError):
        estimate_ground(np.full((3, 3), np.nan), 1.0)
