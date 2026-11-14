# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A synthetic town block with a known answer for every cell (0.5 m cells, 100 m x 100 m).

North-up, rows grow southward. Contents (all heights above flat ground at 20 m):
- a flat-roofed 9 m building (24 x 16 m) with a 6 x 6 m rooftop garden of rough plants;
- a pitched-roof building, 6 to 8 m, brown tiles (14 x 12 m);
- an east-west road 8 m wide with one parked white car;
- five street trees, 10 m tall, 15 m apart, with one missing (a gap), north of the road;
- a park of grass with two trees, a pond, a patch of bare soil, a paved yard.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from avispria.core import landcover as lc

CELL = 0.5
SIZE = 200
GROUND_Z = 20.0


@dataclass
class Scene:
    height: np.ndarray  # above ground
    dsm: np.ndarray
    rgb: np.ndarray
    truth: np.ndarray  # land-cover code per cell


def _m(v: float) -> int:
    return round(v / CELL)


def city(seed: int = 7) -> Scene:
    rng = np.random.default_rng(seed)
    rows, cols = np.mgrid[0:SIZE, 0:SIZE]
    h = np.abs(rng.normal(0, 0.02, (SIZE, SIZE)))
    rgb = np.zeros((SIZE, SIZE, 3))
    truth = np.full((SIZE, SIZE), lc.GRASS, dtype=np.uint8)
    rgb[:] = (110, 160, 70)  # grass everywhere first

    def put(mask: np.ndarray, code: int, colour: tuple[int, int, int]) -> None:
        truth[mask] = code
        rgb[mask] = colour

    yard = (rows >= _m(5)) & (rows < _m(25)) & (cols >= _m(55)) & (cols < _m(95))
    put(yard, lc.PAVED, (175, 172, 168))
    soil = (rows >= _m(5)) & (rows < _m(20)) & (cols >= _m(5)) & (cols < _m(20))
    put(soil, lc.SOIL, (165, 120, 75))
    pond = (rows - _m(85)) ** 2 + (cols - _m(80)) ** 2 <= _m(7) ** 2
    put(pond, lc.WATER, (35, 55, 85))
    road = (rows >= _m(60)) & (rows < _m(68))
    put(road, lc.PAVED, (115, 115, 120))
    car = road & (rows >= _m(61)) & (rows < _m(63)) & (cols >= _m(70)) & (cols < _m(74.5))
    h[car] = 1.5
    put(car, lc.LOW_OBJECT, (235, 235, 235))
    flat = (rows >= _m(30)) & (rows < _m(46)) & (cols >= _m(55)) & (cols < _m(79))
    h[flat] = 9.0 + rng.normal(0, 0.02, flat.sum())
    put(flat, lc.BUILDING, (185, 185, 190))
    garden = (rows >= _m(34)) & (rows < _m(40)) & (cols >= _m(60)) & (cols < _m(66))
    h[garden] = 9.0 + rng.uniform(0.2, 1.0, garden.sum())
    put(garden, lc.ROOF_GREEN, (60, 140, 50))
    pitched = (rows >= _m(30)) & (rows < _m(42)) & (cols >= _m(84)) & (cols < _m(98))
    ridge = _m(36)
    h[pitched] = (8.0 - np.abs(rows - ridge) * CELL * 2.0 / 6.0)[pitched]
    put(pitched, lc.BUILDING, (150, 80, 60))
    for k, x in enumerate((10, 25, 40, 70, 85)):  # 55 is missing: a gap
        crown = (rows - _m(54)) ** 2 + (cols - _m(x)) ** 2 <= _m(3) ** 2
        d = np.sqrt((rows - _m(54)) ** 2 + (cols - _m(x)) ** 2) * CELL
        leafy = 10.0 * np.sqrt(np.clip(1 - (d / 3.0) ** 2, 0, 1)) + rng.normal(0, 0.4, h.shape)
        h[crown] = np.maximum(leafy[crown], 2.6)
        put(crown, lc.TREE, (40 + k, 115, 40))
    for x, y in ((20, 80), (35, 88)):
        crown = (rows - _m(y)) ** 2 + (cols - _m(x)) ** 2 <= _m(4) ** 2
        d = np.sqrt((rows - _m(y)) ** 2 + (cols - _m(x)) ** 2) * CELL
        leafy = 14.0 * np.sqrt(np.clip(1 - (d / 4.0) ** 2, 0, 1)) + rng.normal(0, 0.4, h.shape)
        h[crown] = np.maximum(leafy[crown], 2.6)
        put(crown, lc.TREE, (45, 120, 45))
    rgb = np.clip(rgb + rng.normal(0, 4, rgb.shape), 0, 255)
    return Scene(h, h + GROUND_Z, rgb, truth)


def interior(mask: np.ndarray, cells: int = 3) -> np.ndarray:
    """``mask`` without its edge: where the answer should be certain."""
    from scipy import ndimage as ndi

    return np.asarray(ndi.binary_erosion(mask, iterations=cells))
