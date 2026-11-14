# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Above-ground biomass and carbon of each tree, with the uncertainty carried all the way through.

Two routes from what a drone sees (tree height H in m, crown diameter CD in m):

* Jucker et al. 2017 (Global Change Biology 23:177-190), Eq. 7, made for exactly this:
      AGB [kg] = (0.016 + aG) (H CD)^(2.013 + bG) exp(0.204^2 / 2)
  aG = 0.093, bG = -0.223 for conifers (gymnosperms), 0 for broadleaf trees. Validation spread
  0.69 on the log scale. Plantation and agroforestry trees were not in its data.
* Chave et al. 2014 (Global Change Biology 20:3177-3190), Eq. 4, which needs the stem diameter
  D [cm] and the wood density rho [g/cm3]:
      AGB [kg] = 0.0673 (rho D^2 H)^0.976           (residual spread 0.357 on the log scale)
  D is predicted from the crown with Jucker et al. 2017, Eq. 6:
      D [cm] = 0.557 (H CD)^0.809 exp(0.056^2 / 2)  (validation spread 0.45 on the log scale)
  Jucker et al. found this route about 30 % biased against field biomass, so it is a second
  opinion, not the main number.

Carbon = carbon fraction x AGB (IPCC 2006 default 0.47); CO2 equivalent = carbon x 44/12.

The uncertainty is a Monte Carlo of ``draws`` runs. In each run:
* errors shared by every tree (they do not average out over a stand): the height bias left
  after correction, the wood density (a regional value, not each tree's), the carbon fraction;
* errors of each tree on its own: its ground and height, its crown diameter (outlining), and the
  equation's own scatter (a log-normal factor with mean 1, so the run's average matches the
  published equation).
With a scatter of 0.69 on the log scale, one tree's 95 % range is about 4 times either way of
its middle value (exp(1.96 x 0.69) = 3.9). A stand's total is much tighter, because the trees'
own errors partly cancel, but the shared errors do not.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

JUCKER_SIGMA = 0.69
JUCKER_D_SIGMA = 0.45
CHAVE_SIGMA = 0.357
CO2_PER_C = 44.0 / 12.0
CHUNK = 500


@dataclass(frozen=True)
class BiomassInputs:
    wood_density: float = 0.6  # g/cm3; a regional mean (e.g. from the Global Wood Density Database)
    wood_density_sd: float = 0.1
    carbon_fraction: float = 0.47  # IPCC 2006 default
    carbon_fraction_sd: float = 0.02
    conifer: bool = False  # gymnosperms (Jucker's group terms)
    shared_height_sd_m: float = 0.7  # height bias left after correction (0.7: no field heights)
    crown_rel_sd: float = 0.15  # outlining error of a crown diameter, relative (assumption)
    draws: int = 1000
    seed: int = 0


@dataclass(frozen=True)
class Spread:
    median: float
    low: float  # 2.5 %
    high: float  # 97.5 %


@dataclass(frozen=True)
class TreeBiomass:
    jucker_kg: float  # the published equation's value (point estimate)
    jucker: Spread
    chave_kg: float
    chave: Spread
    co2e: Spread  # kg CO2 equivalent, by the Jucker route


@dataclass(frozen=True)
class StandBiomass:
    trees: list[TreeBiomass]
    agb_kg: Spread  # all trees, Jucker route
    agb_chave_kg: Spread
    carbon_kg: Spread
    co2e_kg: Spread
    band_one_tree: float  # typical high / median of one tree (about 4)
    draws: int


def jucker_agb(h: FloatArray, cd: FloatArray, conifer: bool = False) -> FloatArray:
    a, b = (0.093, -0.223) if conifer else (0.0, 0.0)
    hcd = np.maximum(h * cd, 0.0)
    return np.asarray((0.016 + a) * hcd ** (2.013 + b) * np.exp(0.204**2 / 2), dtype=float)


def jucker_diameter(h: FloatArray, cd: FloatArray) -> FloatArray:
    return np.asarray(0.557 * np.maximum(h * cd, 0.0) ** 0.809 * np.exp(0.056**2 / 2), dtype=float)


def chave_agb(rho: FloatArray, d_cm: FloatArray, h: FloatArray) -> FloatArray:
    return np.asarray(0.0673 * np.maximum(rho * d_cm**2 * h, 0.0) ** 0.976, dtype=float)


def _scatter(rng: np.random.Generator, sigma: float, shape: tuple[int, ...]) -> FloatArray:
    """Log-normal factors with mean 1."""
    return np.exp(rng.normal(-(sigma**2) / 2, sigma, shape))


def _total_spread(values: FloatArray) -> Spread:
    q = np.percentile(values, [50, 2.5, 97.5])
    return Spread(*(round(float(v), 2) for v in q))


def _column_spreads(values: FloatArray) -> list[Spread]:
    q = np.percentile(values, [50, 2.5, 97.5], axis=0)
    return [Spread(*(round(float(v), 2) for v in col)) for col in q.T]


def stand_biomass(
    height_m: FloatArray, crown_m: FloatArray, height_sd_m: FloatArray, inputs: BiomassInputs
) -> StandBiomass:
    """Every tree's biomass with its spread, and the stand's totals.

    ``height_sd_m`` is each tree's own height uncertainty (its ground, mostly); the shared part
    is ``inputs.shared_height_sd_m``. Trees are run in chunks, so a big stand needs little memory.
    """
    h0 = np.asarray(height_m, dtype=float)
    cd0 = np.asarray(crown_m, dtype=float)
    sd0 = np.broadcast_to(np.asarray(height_sd_m, dtype=float), h0.shape)
    n, k = len(h0), inputs.draws
    rng = np.random.default_rng(inputs.seed)
    shared_h = rng.normal(0.0, inputs.shared_height_sd_m, (k, 1))
    rho = np.clip(rng.normal(inputs.wood_density, inputs.wood_density_sd, (k, 1)), 0.1, 1.5)
    cf = np.clip(rng.normal(inputs.carbon_fraction, inputs.carbon_fraction_sd, (k, 1)), 0.3, 0.6)
    sums = np.zeros((3, k))  # Jucker, Chave, CO2e: the stand's total in each run
    trees: list[TreeBiomass] = []
    for start in range(0, n, CHUNK):
        part = slice(start, min(n, start + CHUNK))
        m = part.stop - part.start
        h = np.maximum(h0[part] + shared_h + rng.normal(0.0, 1.0, (k, m)) * sd0[part], 0.5)
        cd = cd0[part] * _scatter(rng, inputs.crown_rel_sd, (k, m))
        jucker = jucker_agb(h, cd, inputs.conifer) * _scatter(rng, JUCKER_SIGMA, (k, m))
        d = jucker_diameter(h, cd) * _scatter(rng, JUCKER_D_SIGMA, (k, m))
        chave = chave_agb(rho, d, h) * _scatter(rng, CHAVE_SIGMA, (k, m))
        co2 = jucker * cf * CO2_PER_C
        sums += np.stack([jucker.sum(axis=1), chave.sum(axis=1), co2.sum(axis=1)])
        j_point = jucker_agb(h0[part], cd0[part], inputs.conifer)
        c_point = chave_agb(
            np.full(m, inputs.wood_density), jucker_diameter(h0[part], cd0[part]), h0[part]
        )
        js, cs, co = (_column_spreads(x) for x in (jucker, chave, co2))
        trees += [
            TreeBiomass(
                round(float(j_point[i]), 2), js[i], round(float(c_point[i]), 2), cs[i], co[i]
            )
            for i in range(m)
        ]
    bands = [t.jucker.high / t.jucker.median for t in trees if t.jucker.median > 0]
    carbon = sums[2] / CO2_PER_C
    return StandBiomass(
        trees,
        _total_spread(sums[0]),
        _total_spread(sums[1]),
        _total_spread(carbon),
        _total_spread(sums[2]),
        round(float(np.median(bands)), 2) if bands else float("nan"),
        k,
    )
