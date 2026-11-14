# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Colour indices from an RGB orthophoto, as relative tools within one flight.

What they are good for: telling green plants from soil, roofs and roads (segmentation), and
finding places that are greener or less green than the rest of the same flight, or than the same
place in an earlier flight once both are ranked within their own flight (change).

What they are not: measures of chlorophyll, nitrogen, or water. A drone's JPEG colours have been
through the camera's own tone curve, white balance, sharpening and noise reduction, which change
with the scene; they cannot be turned back into reflectance (Burggraaff et al. 2019). So:
* every index is computed on the colours as they are, with no "linearisation";
* the numbers are compared only within one flight; between flights, each flight's values are
  ranked (percentiles) first, and only the ranks are compared;
* indices defined on reflectance (VARI, TGI) are labelled as approximations.

The indices (r, g, b are chromatic coordinates R/(R+G+B) etc.; they cancel overall brightness):
  ExG    2g - r - b                          Woebbecke et al. 1995
  ExR    1.4r - g                            Meyer & Camargo Neto 2008
  ExGR   ExG - ExR (> 0: vegetation)        Meyer & Camargo Neto 2008
  GLI    (2G - R - B) / (2G + R + B)         Louhaichi et al. 2001
  NGRDI  (G - R) / (G + R)                   Tucker 1979
  MGRVI  (G^2 - R^2) / (G^2 + R^2)           Bendig et al. 2015
  RGBVI  (G^2 - R B) / (G^2 + R B)           Bendig et al. 2015
  VARI   (G - R) / (G + R - B), clipped      Gitelson et al. 2002 (on reflectance: approximate)
  TGI    G - 0.39R - 0.61B (generic camera)  Hunt et al. 2013 (approximate band centres)
  GCC    g (green chromatic coordinate)      used for crown condition (e.g. ash dieback)
  RCC    r
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
EPS = 1e-6


def _chroma(rgb: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
    total = rgb.sum(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = rgb / np.where(total > EPS, total, np.nan)[..., None]
    return out[..., 0], out[..., 1], out[..., 2]


def _ratio(num: FloatArray, den: FloatArray, clip: float = 1.0) -> FloatArray:
    with np.errstate(invalid="ignore", divide="ignore"):
        value = np.where(np.abs(den) > EPS, num / den, np.nan)
    return np.clip(value, -clip, clip)


def _rgb(rgb: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
    v = rgb / 255.0 if np.nanmax(rgb) > 1.5 else rgb
    return v[..., 0], v[..., 1], v[..., 2]


def exg(rgb: FloatArray) -> FloatArray:
    r, g, b = _chroma(rgb)
    return 2 * g - r - b


def exr(rgb: FloatArray) -> FloatArray:
    r, g, _ = _chroma(rgb)
    return 1.4 * r - g


def exgr(rgb: FloatArray) -> FloatArray:
    return exg(rgb) - exr(rgb)


def gli(rgb: FloatArray) -> FloatArray:
    r, g, b = _rgb(rgb)
    return _ratio(2 * g - r - b, 2 * g + r + b)


def ngrdi(rgb: FloatArray) -> FloatArray:
    r, g, _ = _rgb(rgb)
    return _ratio(g - r, g + r)


def mgrvi(rgb: FloatArray) -> FloatArray:
    r, g, _ = _rgb(rgb)
    return _ratio(g**2 - r**2, g**2 + r**2)


def rgbvi(rgb: FloatArray) -> FloatArray:
    r, g, b = _rgb(rgb)
    return _ratio(g**2 - r * b, g**2 + r * b)


def vari(rgb: FloatArray) -> FloatArray:
    r, g, b = _rgb(rgb)
    return _ratio(g - r, g + r - b)  # the denominator nears 0 in bluish shadow: clipped to +-1


def tgi(rgb: FloatArray) -> FloatArray:
    r, g, b = _rgb(rgb)
    return g - 0.39 * r - 0.61 * b


def gcc(rgb: FloatArray) -> FloatArray:
    return _chroma(rgb)[1]


def rcc(rgb: FloatArray) -> FloatArray:
    return _chroma(rgb)[0]


INDICES: dict[str, tuple[Callable[[FloatArray], FloatArray], str]] = {
    "exg": (exg, "excess green 2g-r-b"),
    "exr": (exr, "excess red 1.4r-g"),
    "exgr": (exgr, "excess green minus excess red; > 0 is vegetation"),
    "gli": (gli, "green leaf index"),
    "ngrdi": (ngrdi, "normalised green-red difference"),
    "mgrvi": (mgrvi, "modified green-red vegetation index"),
    "rgbvi": (rgbvi, "red-green-blue vegetation index"),
    "vari": (vari, "visible atmospherically resistant index (defined on reflectance: approximate)"),
    "tgi": (tgi, "triangular greenness, generic camera band centres (approximate)"),
    "gcc": (gcc, "green chromatic coordinate"),
    "rcc": (rcc, "red chromatic coordinate"),
}
CAVEAT = (
    "relative within this flight: JPEG colours are not reflectance, so these values cannot be "
    "compared with other flights, other cameras or published thresholds; compare flights only "
    "by their within-flight ranks (percentiles)"
)


def otsu(values: FloatArray, bins: int = 256) -> float:
    """The threshold that best splits ``values`` in two (Otsu 1979)."""
    v = values[np.isfinite(values)]
    if v.size == 0 or np.ptp(v) == 0:
        return float("nan")
    hist, edges = np.histogram(v, bins=bins)
    mids = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * mids) / np.maximum(w0, 1)
    m1 = (np.sum(hist * mids) - np.cumsum(hist * mids)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(mids[int(np.argmax(between))])


def vegetation_mask(rgb: FloatArray) -> tuple[BoolArray, str]:
    """Green plants: ExGR > 0 (a fixed, tested threshold), else ExG above Otsu's threshold when
    ExGR finds almost nothing (very dull or tinted photos)."""
    v = exgr(rgb)
    mask = np.nan_to_num(v) > 0
    if mask.mean() >= 0.01 or not np.isfinite(v).any():
        return mask, "ExGR > 0"
    e = exg(rgb)
    t = otsu(e)
    return np.nan_to_num(e, nan=-1) > t, f"ExG > {t:.3f} (Otsu, this flight only)"


def percentile_rank(values: FloatArray) -> FloatArray:
    """Each value's rank within its own flight, 0..100 (NaN stays NaN)."""
    out = np.full(values.shape, np.nan)
    ok = np.isfinite(values)
    if ok.any():
        order = values[ok].argsort(kind="stable")
        ranks = np.empty(order.size)
        ranks[order] = np.arange(order.size)
        out[ok] = 100.0 * ranks / max(1, order.size - 1)
    return out


def rank_change(before: FloatArray, after: FloatArray) -> FloatArray:
    """Change between two flights of the same place (same grid): the difference of each value's
    rank within its own flight. -30 means a place fell 30 percentile points against the rest of
    its flight. Only what changed relative to the rest can be seen this way, not a change of the
    whole area (light and camera differ between flights)."""
    both = np.isfinite(before) & np.isfinite(after)
    a = percentile_rank(np.where(both, before, np.nan))
    b = percentile_rank(np.where(both, after, np.nan))
    return b - a


def flight_summary(values: FloatArray) -> dict[str, float | None]:
    v = values[np.isfinite(values)]
    if v.size == 0:
        return {"p5": None, "p50": None, "p95": None}
    p5, p50, p95 = np.percentile(v, [5, 50, 95])
    return {"p5": round(float(p5), 4), "p50": round(float(p50), 4), "p95": round(float(p95), 4)}
