# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a map image should look like: size, resolution and furniture, checked before drawing.

Sizes are in millimetres, as journals give them; the resolution in dots per inch. The preview is
drawn from the same description at a low resolution, so it shows exactly the layout that will be
saved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MM_PER_INCH = 25.4
WIDTHS_MM: dict[str, float] = {
    "Journal, 1 column (85 mm)": 85.0,
    "Journal, 1.5 columns (120 mm)": 120.0,
    "Journal, 2 columns (170 mm)": 170.0,
    "A4 page (180 mm)": 180.0,
    "A3 poster panel (270 mm)": 270.0,
}
DPIS = (150, 300, 600, 1200)
FORMATS = ("png", "tif", "pdf", "svg")  # pdf and svg keep text and furniture as vectors
MIN_MM, MAX_MM = 20.0, 600.0
MIN_DPI, MAX_DPI = 72, 1200
MAX_PIXELS = 250_000_000  # beyond this an image is too big for most programs to open
PREVIEW_DPI = 90
RAMP_NAMES = ("greens", "viridis", "terrain", "diverging", "magma", "grey")


class FigureError(ValueError):
    """The description cannot be drawn; the message says what to change."""


@dataclass(frozen=True)
class FigureSpec:
    layer: str  # a key of the available layers (figure.layers)
    width_mm: float = 170.0
    height_mm: float | None = None  # None: as tall as the map needs
    dpi: int = 300
    title: str = ""
    caption: str = ""
    legend: bool = True  # colour bar, or class legend for land cover
    north_arrow: bool = True
    scale_bar: bool = True
    grid: bool = True  # coordinate ticks in metres
    crowns: bool = False  # tree crown outlines on top
    ramp: str = ""  # '' = the layer's own colours
    low: float | None = None  # colour range; None = from the data (2nd-98th percentile)
    high: float | None = None
    font_pt: float = 8.0
    fmt: str = "png"

    def checked(self) -> FigureSpec:
        if not self.layer:
            raise FigureError("Choose a map layer.")
        for name, value in (("width", self.width_mm), ("height", self.height_mm)):
            if value is not None and not MIN_MM <= value <= MAX_MM:
                raise FigureError(f"The {name} must be {MIN_MM:.0f} to {MAX_MM:.0f} mm.")
        if not MIN_DPI <= self.dpi <= MAX_DPI:
            raise FigureError(f"The resolution must be {MIN_DPI} to {MAX_DPI} dpi.")
        if self.fmt not in FORMATS:
            raise FigureError(f"Save as one of: {', '.join(FORMATS)}.")
        if self.ramp and self.ramp not in RAMP_NAMES:
            raise FigureError(f"Colours: one of {', '.join(RAMP_NAMES)}.")
        if self.low is not None and self.high is not None and self.high <= self.low:
            raise FigureError("The top of the colour range must be above the bottom.")
        if not 5.0 <= self.font_pt <= 24.0:
            raise FigureError("Text size: 5 to 24 pt.")
        height = self.height_mm or self.width_mm
        if pixels(self.width_mm, self.dpi) * pixels(height, self.dpi) > MAX_PIXELS:
            raise FigureError(
                "That is too many pixels for most programs to open: lower the resolution or the "
                "size, or save as PDF or SVG."
            )
        return self


def pixels(mm: float, dpi: int) -> int:
    return max(1, round(mm / MM_PER_INCH * dpi))


def inches(mm: float) -> float:
    return mm / MM_PER_INCH


def auto_height_mm(
    width_mm: float,
    map_ratio: float,
    *,
    title: bool = False,
    caption_lines: int = 0,
    grid: bool = True,
    legend: str = "bar",
    legend_chars: int = 24,
    font_pt: float = 8.0,
) -> float:
    """The height that fits the map's shape (height / width) with no empty bands.

    ``legend`` is bar (a colour bar on the right), classes (a class list on the right) or none.
    The margins are what the axis labels, colour bar, title and caption take, in millimetres.
    """
    text_mm = font_pt * 0.3528  # one line of text
    classes = (legend_chars * 0.55 + 5) * text_mm  # the longest class name, and its swatch
    side = {"bar": 9 * text_mm, "classes": classes, "none": 2.0}.get(legend, 2.0)
    left = 10 * text_mm if grid else 2.0
    map_width = max(10.0, width_mm - left - side)
    top = (2.2 * text_mm if title else 0.0) + 3.0
    bottom = (4.2 * text_mm if grid else 2.0) + caption_lines * 1.3 * text_mm
    return round(min(MAX_MM, max(MIN_MM, map_width * map_ratio + top + bottom)), 1)


def nice_length(span_m: float, fraction: float = 0.25) -> float:
    """A round scale-bar length (1, 2 or 5 times a power of ten) near ``fraction`` of the span."""
    if span_m <= 0:
        raise FigureError("The map has no extent.")
    target = span_m * fraction
    power = 10 ** math.floor(math.log10(target))
    for step in (5, 2, 1):
        if step * power <= target:
            return float(step * power)
    return float(power)


def length_label(metres: float) -> str:
    return f"{metres / 1000:g} km" if metres >= 1000 else f"{metres:g} m"
