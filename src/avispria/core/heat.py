# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Relative heat exposure from an RGB map and its surface model. Not temperature.

An RGB camera does not see emitted heat, so no number here is in degrees. What a daytime surface
gains in heat is mostly set by three things that the RGB map and the surface model do show:

* how long it is in direct sun (the surface model casts the shadows of trees and buildings);
* how much of that sun it absorbs, one minus its albedo. For surfaces that are not green, camera
  brightness within the flight is mapped onto a typical albedo range of built and bare surfaces
  (0.05 for the darkest to 0.45 for the brightest). Green leaves look dark to a camera but reflect
  strongly in the near infrared, so their brightness says little about their albedo: green
  vegetation is given a fixed typical albedo instead;
* whether it is green vegetation, which loses heat by transpiration.

The heat index is their product, ranked within the flight (0 = least exposed, 1 = most). How much
open sky each point sees (sky view factor, Dozier & Frew 1990) is given as its own band: it governs
how fast a surface cools at night and is not part of the daytime index. Every part is a separate
band, so it can be recombined or checked against thermal measurements elsewhere. Validate against
a thermal camera before reporting any heat result.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from avispria.core.shade import shadow_mask

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

HOURS = tuple(range(9, 17))  # 09:00 to 16:00 local time, hourly
VEGETATION_COOLING = 0.6  # share of absorbed sun a green cell is taken not to turn into heat
VEGETATION_ALBEDO = 0.18  # typical broadband albedo of green vegetation (about 0.15-0.25)
ALBEDO_RANGE = (0.05, 0.45)  # darkest to brightest non-green surface in a flight
DIRECTIONS = 16
SKY_RADIUS_M = 40.0
SUN_CELL_M = 0.5  # shadows are cast on a grid this coarse (or the map's own, if coarser)
SKY_CELL_M = 1.0  # the sky view is computed on a grid this coarse
METHOD = (
    "relative daytime heat exposure = sun hours (09:00-16:00, shadows from the surface model) x "
    f"(1 - albedo) x (1 - {VEGETATION_COOLING} x green vegetation), ranked within the flight; "
    f"albedo {VEGETATION_ALBEDO} for green vegetation, otherwise {ALBEDO_RANGE[0]}-"
    f"{ALBEDO_RANGE[1]} from relative brightness; not temperature"
)


@dataclass(frozen=True)
class HeatParts:
    sun_hours: FloatArray  # share of HOURS in direct sun, 0..1
    brightness: FloatArray  # relative brightness within the flight, 0..1
    albedo: FloatArray  # assumed broadband albedo (see the module text)
    vegetation: FloatArray  # 1 green vegetation, 0 not
    sky_view: FloatArray  # sky view factor, 0..1
    index: FloatArray  # heat exposure ranked within the flight, 0..1
    hours_used: int  # sun positions above the horizon


def sun_hours(
    surface: FloatArray, cell_m: float, suns: Sequence[tuple[float, float]]
) -> FloatArray:
    """Share of the sun positions (elevation, azimuth) in which each cell is in direct sun."""
    valid = np.isfinite(surface)
    up = [(e, a) for e, a in suns if e > 0]
    if not up:
        return np.where(valid, 0.0, np.nan)
    lit = np.zeros(surface.shape)
    for elevation, azimuth in up:
        lit += ~shadow_mask(surface, cell_m, elevation, azimuth)
    return np.where(valid, lit / len(up), np.nan)


def brightness(rgb: FloatArray) -> FloatArray:
    """Luminance (Rec. 709 weights) scaled to 0..1 between the flight's 2nd and 98th percentile."""
    lum: FloatArray = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    ok = np.isfinite(lum)
    if not ok.any():
        return lum
    low, high = np.percentile(lum[ok], [2, 98])
    scaled: FloatArray = np.clip((lum - low) / max(float(high - low), 1e-9), 0.0, 1.0)
    return scaled


def _shift(values: FloatArray, dy: int, dx: int) -> FloatArray:
    out = np.full(values.shape, np.nan)
    h, w = values.shape
    if abs(dy) >= h or abs(dx) >= w:
        return out
    ys, yd = (slice(dy, h), slice(0, h - dy)) if dy >= 0 else (slice(0, h + dy), slice(-dy, h))
    xs, xd = (slice(dx, w), slice(0, w - dx)) if dx >= 0 else (slice(0, w + dx), slice(-dx, w))
    out[yd, xd] = values[ys, xs]
    return out


def sky_view(
    surface: FloatArray, cell_m: float, radius_m: float = SKY_RADIUS_M, directions: int = DIRECTIONS
) -> FloatArray:
    """Sky view factor of a level surface: mean over directions of cos² of the horizon angle.

    The horizon in each direction is the steepest rise of the surface within ``radius_m``. Near
    the edge of the map the horizon is only what the map shows, so the edge looks more open.
    """
    if cell_m <= 0:
        raise ValueError("cell_m must be positive")
    valid = np.isfinite(surface)
    steps = max(1, int(radius_m / cell_m))
    total = np.zeros(surface.shape)
    for k in range(directions):
        angle = 2 * math.pi * k / directions
        east, north = math.sin(angle), math.cos(angle)
        steepest = np.zeros(surface.shape)
        for step in range(1, steps + 1):
            dx, dy = round(step * east), round(-step * north)
            if dx == 0 and dy == 0:
                continue
            ahead = _shift(surface, dy, dx)
            distance = math.hypot(dx, dy) * cell_m
            rise = np.nan_to_num((ahead - surface) / distance, nan=0.0)
            steepest = np.maximum(steepest, rise)
        total += np.cos(np.arctan(steepest)) ** 2
    return np.where(valid, total / directions, np.nan)


def coarse(values: FloatArray, factor: int) -> FloatArray:
    """Block means over ``factor`` x ``factor`` cells (NaN ignored; all-NaN blocks stay NaN)."""
    if factor <= 1:
        return values
    h, w = values.shape
    padded = np.full((-(-h // factor) * factor, -(-w // factor) * factor), np.nan)
    padded[:h, :w] = values
    blocks = padded.reshape(padded.shape[0] // factor, factor, padded.shape[1] // factor, factor)
    ok = np.isfinite(blocks)
    count = ok.sum(axis=(1, 3))
    total = np.where(ok, blocks, 0.0).sum(axis=(1, 3))
    return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def fine(values: FloatArray, factor: int, shape: tuple[int, int]) -> FloatArray:
    """Back to the map's grid: each coarse cell repeated, cut to ``shape``."""
    if factor <= 1:
        return values
    out: FloatArray = np.repeat(np.repeat(values, factor, axis=0), factor, axis=1)
    return out[: shape[0], : shape[1]]


def on_coarse(surface: FloatArray, cell_m: float, target_m: float) -> tuple[FloatArray, float, int]:
    factor = max(1, round(target_m / cell_m))
    return coarse(surface, factor), cell_m * factor, factor


def ranked(values: FloatArray) -> FloatArray:
    """Each value's rank within the flight, 0..1 (NaN stays NaN)."""
    out = np.full(values.shape, np.nan)
    ok = np.isfinite(values)
    if ok.any():
        order = values[ok].argsort(kind="stable")
        ranks = np.empty(order.size)
        ranks[order] = np.arange(order.size)
        out[ok] = ranks / max(1, order.size - 1)
    return out


def heat_parts(
    surface: FloatArray,
    rgb: FloatArray,
    vegetation: BoolArray,
    cell_m: float,
    suns: Sequence[tuple[float, float]],
) -> HeatParts:
    """Every band of the heat exposure for one map (all arrays on the same grid)."""
    valid = np.isfinite(surface)
    sun_grid, sun_cell, f_sun = on_coarse(surface, cell_m, SUN_CELL_M)
    hours = fine(sun_hours(sun_grid, sun_cell, suns), f_sun, surface.shape)
    hours = np.where(valid, hours, np.nan)
    sky_grid, sky_cell, f_sky = on_coarse(surface, cell_m, SKY_CELL_M)
    sky = np.where(valid, fine(sky_view(sky_grid, sky_cell), f_sky, surface.shape), np.nan)
    bright = brightness(rgb)
    green = np.where(np.isfinite(bright), vegetation.astype(float), np.nan)
    low, high = ALBEDO_RANGE
    albedo = np.where(green == 1, VEGETATION_ALBEDO, low + (high - low) * bright)
    raw = hours * (1.0 - albedo) * (1.0 - VEGETATION_COOLING * green)
    return HeatParts(
        sun_hours=hours,
        brightness=bright,
        albedo=albedo,
        vegetation=green,
        sky_view=sky,
        index=ranked(raw),
        hours_used=sum(1 for e, _ in suns if e > 0),
    )


def summary(parts: HeatParts) -> dict[str, float | int | None]:
    """Means for the record; the index is a rank, so only its spread between parts is shown."""

    def mean(values: FloatArray, where: BoolArray | None = None) -> float | None:
        ok = np.isfinite(values) if where is None else np.isfinite(values) & where
        return round(float(values[ok].mean()), 3) if ok.any() else None

    green = parts.vegetation == 1
    other = parts.vegetation == 0
    return {
        "sun_positions": parts.hours_used,
        "sun_hours_share_mean": mean(parts.sun_hours),
        "sky_view_mean": mean(parts.sky_view),
        "index_mean_green": mean(parts.index, green),
        "index_mean_not_green": mean(parts.index, other),
    }
