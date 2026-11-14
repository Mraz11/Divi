# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ground sources, doming, height correction, biomass, colour indices, symptoms, CHM quality."""

import numpy as np
import pytest

from avispria.core.biomass import (
    BiomassInputs,
    chave_agb,
    jucker_agb,
    jucker_diameter,
    stand_biomass,
)
from avispria.core.chm_quality import check_chm
from avispria.core.doming import check_doming, not_checked
from avispria.core.ground_sources import (
    GroundChoice,
    align,
    describe_choice,
    distance_to_seen,
    ground_sigma,
    rank,
    seen_ground,
)
from avispria.core.height_calibration import NONE, calibrate
from avispria.core.indices import (
    INDICES,
    exgr,
    flight_summary,
    otsu,
    percentile_rank,
    rank_change,
    vari,
    vegetation_mask,
)
from avispria.core.symptoms import crown_symptoms

# ------------------------------------------------------------------------- ground sources


def test_the_best_ground_source_comes_first_and_global_wins_under_closed_canopy() -> None:
    kinds = ["estimated", "engine", "global", "lidar"]
    assert rank(kinds, seen_pct=40) == ["lidar", "engine", "global", "estimated"]
    assert rank(kinds, seen_pct=3) == ["lidar", "global", "engine", "estimated"]
    with pytest.raises(ValueError, match="unknown"):
        rank(["drone"], 50)


def test_an_outside_model_is_moved_to_meet_the_flight() -> None:
    dsm = np.full((20, 20), 100.0)
    outside = np.full((20, 20), 52.5)  # a geoid model 47.5 m lower
    seen = np.ones((20, 20), bool)
    moved, shift, n = align(outside, dsm, seen)
    assert shift == pytest.approx(47.5) and n == 400 and np.allclose(moved, 100.0)
    _, none, few = align(outside, dsm, np.zeros((20, 20), bool))
    assert none == 0.0 and few == 0
    choice = GroundChoice("global", 5, ("global",), 47.5, 400, 3.0, "")
    assert "moved +47.50 m" in describe_choice(choice)
    assert "check its datum" in describe_choice(GroundChoice("lidar", 1, (), 0, 3, 3.0, ""))


def test_the_ground_is_less_sure_far_from_where_it_was_seen() -> None:
    dsm = np.full((1, 50), 10.0)
    ground = dsm.copy()
    ground[0, 10:] = 5.0  # surface 5 m above: canopy from cell 10 on
    seen = seen_ground(dsm, ground)
    d = distance_to_seen(seen, cell_m=1.0)
    assert d[0, 0] == 0 and d[0, 49] == 40
    s = ground_sigma("engine", d)
    assert s[0, 0] == pytest.approx(0.3) and s[0, 49] > s[0, 20] > s[0, 0]
    assert np.all(ground_sigma("lidar", d) == 0.15)
    assert np.isinf(distance_to_seen(np.zeros((3, 3), bool), 1.0)).all()


# ------------------------------------------------------------------------------- doming


def _dome(amplitude: float, noise: float = 0.05) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows, cols = np.mgrid[0:80, 0:80]
    r2 = ((rows - 39.5) ** 2 + (cols - 39.5) ** 2) / (39.5**2 * 2)
    ref = 30.0 + 0.01 * cols
    rng = np.random.default_rng(1)
    ground = ref + 3.0 + amplitude * (1 - r2) + rng.normal(0, noise, ref.shape)
    return ground, ref, np.ones(ref.shape, bool)


def test_a_dome_is_found_and_a_flat_model_is_not() -> None:
    domed = check_doming(*_dome(1.5), cell_m=1.0)
    assert domed.checked and domed.domed and domed.dome_m == pytest.approx(1.5, abs=0.1)
    assert "dome (middle too high)" in domed.note
    bowl = check_doming(*_dome(-1.0), cell_m=1.0)
    assert bowl.domed and bowl.dome_m < 0 and "bowl" in bowl.note
    flat = check_doming(*_dome(0.0), cell_m=1.0)
    assert flat.checked and not flat.domed


def test_doming_needs_enough_spread_out_ground() -> None:
    g, ref, seen = _dome(1.0)
    few = np.zeros_like(seen)
    few[:5, :5] = True
    assert not check_doming(g, ref, few, 1.0).checked
    corner = np.zeros_like(seen)
    corner[:20, :20] = True
    assert "one corner" in check_doming(g, ref, corner, 1.0).note
    assert not not_checked().checked


# --------------------------------------------------------------------- height correction


def _tops(n: int) -> tuple[np.ndarray, np.ndarray]:
    xy = np.column_stack([np.arange(n) * 10.0, np.zeros(n)])
    return xy, np.linspace(8, 25, n)


def test_five_field_trees_give_a_line_and_fewer_an_offset() -> None:
    xy, h = _tops(8)
    truth = 1.5 + 1.1 * h  # the model reads low, more so for tall trees
    field = [(f"t{i}", xy[i, 0] + 1, xy[i, 1], truth[i]) for i in range(8)]
    cal = calibrate(xy, h, field)
    assert cal.method == "line" and cal.matched == 8
    assert cal.slope == pytest.approx(1.1, abs=1e-3) and cal.rmse_after_m == pytest.approx(0)
    assert cal.rmse_before_m > 2 and np.allclose(cal.apply(h), truth)
    off = calibrate(xy, h, field[:3])
    assert off.method == "offset" and off.slope == 1.0 and off.rmse_loo_m is not None
    one = calibrate(xy, h, field[:1])
    assert one.method == "none" and "2 needed" in one.note
    far = calibrate(xy, h, [("x", 999.0, 999.0, 10.0)])
    assert far.unmatched == 1 and far.method == "none"
    assert calibrate(xy, h, []) is NONE


def test_an_implausible_slope_falls_back_to_an_offset() -> None:
    xy, h = _tops(6)
    field = [(str(i), xy[i, 0], 0.0, 30.0 - h[i]) for i in range(6)]  # negative slope
    assert calibrate(xy, h, field).method == "offset"


# ------------------------------------------------------------------------------ biomass


def test_the_published_equations() -> None:
    # Jucker Eq. 7, broadleaf: 0.016 (20 x 8)^2.013 exp(0.204^2/2)
    assert jucker_agb(np.array([20.0]), np.array([8.0]))[0] == pytest.approx(
        0.016 * 160**2.013 * np.exp(0.204**2 / 2)
    )
    conifer = jucker_agb(np.array([20.0]), np.array([8.0]), conifer=True)[0]
    assert conifer == pytest.approx(0.109 * 160**1.790 * np.exp(0.204**2 / 2))
    assert jucker_diameter(np.array([20.0]), np.array([8.0]))[0] == pytest.approx(
        0.557 * 160**0.809 * np.exp(0.056**2 / 2)
    )
    assert chave_agb(np.array([0.6]), np.array([30.0]), np.array([20.0]))[0] == pytest.approx(
        0.0673 * (0.6 * 900 * 20) ** 0.976
    )


def test_one_tree_is_about_four_times_uncertain_and_a_stand_is_tighter() -> None:
    n = 200
    rng = np.random.default_rng(3)
    h, cd = rng.uniform(10, 25, n), rng.uniform(4, 10, n)
    stand = stand_biomass(h, cd, np.full(n, 0.5), BiomassInputs(draws=800))
    assert 3.3 < stand.band_one_tree < 5.0
    total = stand.agb_kg
    assert (total.high - total.low) / total.median < 1.0  # far tighter than one tree
    point = float(jucker_agb(h, cd).sum())
    assert total.low < point < total.high
    assert stand.co2e_kg.median == pytest.approx(stand.carbon_kg.median * 44 / 12, rel=0.02)
    assert stand.trees[0].jucker.low < stand.trees[0].jucker_kg < stand.trees[0].jucker.high


def test_the_same_seed_gives_the_same_answer_and_no_trees_is_fine() -> None:
    h, cd = np.array([12.0, 18.0]), np.array([5.0, 7.0])
    a = stand_biomass(h, cd, np.array([0.3, 0.3]), BiomassInputs(draws=200, seed=4))
    b = stand_biomass(h, cd, np.array([0.3, 0.3]), BiomassInputs(draws=200, seed=4))
    assert a.agb_kg == b.agb_kg
    empty = stand_biomass(np.array([]), np.array([]), np.array([]), BiomassInputs(draws=50))
    assert empty.trees == [] and empty.agb_kg.median == 0 and np.isnan(empty.band_one_tree)


# ------------------------------------------------------------------------------- indices


def _scene() -> np.ndarray:
    rgb = np.zeros((10, 10, 3))
    rgb[:5] = (60, 160, 50)  # leaves
    rgb[5:] = (150, 120, 90)  # soil
    return rgb


def test_indices_separate_leaves_from_soil() -> None:
    rgb = _scene()
    for name, (fn, _) in INDICES.items():
        values = fn(rgb)
        assert values.shape == (10, 10), name
        if name not in ("exr", "rcc"):
            assert values[0, 0] > values[9, 9], name
    mask, rule = vegetation_mask(rgb)
    assert rule == "ExGR > 0" and mask[:5].all() and not mask[5:].any()
    assert (exgr(rgb)[:5] > 0).all()
    assert np.isfinite(vari(np.full((2, 2, 3), 80.0))).all()  # a zero denominator is clipped


def test_dull_photos_fall_back_to_otsu_and_flights_compare_by_rank() -> None:
    dull = np.full((10, 10, 3), 100.0)
    dull[:5, :, 1] = 104.0
    mask, rule = vegetation_mask(dull)
    assert "Otsu" in rule and mask[:5].all() and not mask[5:].any()
    assert np.isnan(otsu(np.full(4, 1.0)))
    before = np.arange(10.0)
    after = before * 3 + 50  # all brighter: no change in rank
    assert np.allclose(rank_change(before, after), 0)
    after[0] = 1000.0  # the lowest place became the highest
    assert rank_change(before, after)[0] == pytest.approx(100)
    assert np.isnan(percentile_rank(np.array([np.nan]))).all()
    assert flight_summary(np.array([np.nan]))["p50"] is None


# ------------------------------------------------------------------------------ symptoms


def test_a_brown_crown_among_green_ones_is_a_candidate() -> None:
    labels = np.zeros((40, 40), np.int32)
    rgb = np.zeros((40, 40, 3))
    for k in range(16):
        r, c = divmod(k, 4)
        labels[r * 10 : r * 10 + 8, c * 10 : c * 10 + 8] = k + 1
        rgb[r * 10 : r * 10 + 8, c * 10 : c * 10 + 8] = (60 + k, 150, 50)
    rgb[labels == 16] = (140, 110, 70)  # one brown crown
    report = crown_symptoms(labels, rgb, list(range(1, 17)), {3}, 0.5, low_sun=True)
    flagged = {c.crown_id for c in report.crowns if c.candidate}
    assert flagged == {3, 16}
    assert report.candidates == 2 and report.candidate_area_pct == pytest.approx(12.5)
    assert any("latent infection" in n for n in report.notes)
    assert any("sun was low" in n for n in report.notes)
    few = crown_symptoms(labels, rgb, [1, 2], set(), 0.5)
    assert all(c.gcc_z is None for c in few.crowns)
    assert crown_symptoms(labels, rgb, [], set(), 0.5).candidates == 0


# ----------------------------------------------------------------------------- quality


def test_the_quality_grade() -> None:
    dsm = np.full((50, 50), 20.0)
    ground = np.full((50, 50), 10.0)
    inside = np.ones((50, 50), bool)
    good = check_chm(dsm, ground, inside, 40.0, np.array([0.4]), not_checked(), False)
    assert good.grade == "good" and any("doming not checked" in f for f in good.findings)
    holes = dsm.copy()
    holes[:15] = np.nan
    poor = check_chm(holes, ground, inside, 40.0, np.array([0.4]), not_checked(), False)
    assert poor.grade == "poor" and poor.holes_pct == 30
    closed = check_chm(dsm, ground, inside, 3.0, np.array([2.0]), not_checked(), False)
    assert closed.grade == "use with care" and len(closed.findings) == 3
    lidar = check_chm(dsm, ground, inside, 3.0, np.array([0.15]), not_checked(), True)
    assert lidar.grade == "good"
    above = check_chm(dsm, ground + 15, inside, 40.0, np.array([0.4]), not_checked(), False)
    assert above.grade == "poor" and above.ground_above_pct == 100
    spiky = dsm.copy()
    spiky[0, :3] = 200.0
    assert check_chm(spiky, ground, inside, 40, np.array([0.4]), not_checked(), False).spikes_pct
    domed = check_doming(*_dome(3.0), cell_m=1.0)
    assert check_chm(dsm, ground, inside, 40, np.array([]), domed, False).grade == "poor"
