# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""QGIS style files (QML), so every exported layer opens in QGIS already styled.

QGIS loads ``name.qml`` next to ``name.tif`` as the layer's default style, and a GeoPackage's
``layer_styles`` table for vector layers. These are plain XML strings; QGIS falls back to its own
default style if it cannot read one, so a style can never stop a layer from opening.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

Ramp = Sequence[tuple[float, str]]  # (position 0..1, "#rrggbb")

# perceptually ordered ramps (colour-blind safe where it matters)
GREENS: Ramp = (
    (0.0, "#f7fcf5"),
    (0.25, "#c7e9c0"),
    (0.5, "#74c476"),
    (0.75, "#238b45"),
    (1.0, "#00441b"),
)
VIRIDIS: Ramp = (
    (0.0, "#440154"),
    (0.25, "#3b528b"),
    (0.5, "#21918c"),
    (0.75, "#5ec962"),
    (1.0, "#fde725"),
)
TERRAIN: Ramp = (
    (0.0, "#2b4a2e"),
    (0.3, "#8aa86a"),
    (0.6, "#d8c48a"),
    (0.85, "#a07850"),
    (1.0, "#f4f1ec"),
)
DIVERGING: Ramp = (
    (0.0, "#a50026"),
    (0.25, "#f46d43"),
    (0.5, "#ffffbf"),
    (0.75, "#66bd63"),
    (1.0, "#006837"),
)
MAGMA: Ramp = (
    (0.0, "#000004"),
    (0.25, "#51127c"),
    (0.5, "#b73779"),
    (0.75, "#fc8961"),
    (1.0, "#fcfdbf"),
)
GREY: Ramp = ((0.0, "#000000"), (1.0, "#ffffff"))
RAMPS: dict[str, Ramp] = {
    "greens": GREENS,
    "viridis": VIRIDIS,
    "terrain": TERRAIN,
    "diverging": DIVERGING,
    "magma": MAGMA,
    "grey": GREY,
}

HEAD = "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"


def _rgb(colour: str) -> str:
    c = colour.lstrip("#")
    return ",".join(str(int(c[i : i + 2], 16)) for i in (0, 2, 4))


def pseudocolor(low: float, high: float, ramp: Ramp, unit: str = "") -> str:
    """A one-band raster coloured along ``ramp`` from ``low`` to ``high``."""
    span = high - low if high > low else 1.0
    items = "".join(
        f'<item alpha="255" value="{low + t * span:.4g}" color="{c}" '
        f'label="{escape(f"{low + t * span:.4g} {unit}".strip())}"/>'
        for t, c in ramp
    )
    return (
        f'{HEAD}<qgis version="3.28" styleCategories="AllStyleCategories"><pipe>'
        f'<rasterrenderer type="singlebandpseudocolor" band="1" opacity="1" alphaBand="-1" '
        f'classificationMin="{low:.4g}" classificationMax="{high:.4g}" nodataColor="">'
        f'<rastershader><colorrampshader colorRampType="INTERPOLATED" classificationMode="1" '
        f'clip="0" minimumValue="{low:.4g}" maximumValue="{high:.4g}">{items}'
        "</colorrampshader></rastershader></rasterrenderer></pipe>"
        "<blendMode>0</blendMode></qgis>\n"
    )


def _option(name: str, value: str) -> str:
    return f'<Option name="{name}" value="{escape(value)}" type="QString"/>'


def _symbol(kind: str, colour: str, outline: str, size: float) -> str:
    if kind == "point":
        layer = (
            '<layer class="SimpleMarker" enabled="1" pass="0" locked="0"><Option type="Map">'
            + _option("name", "circle")
            + _option("color", f"{_rgb(colour)},255")
            + _option("outline_color", f"{_rgb(outline)},255")
            + _option("outline_width", "0.2")
            + _option("size", f"{size}")
            + "</Option></layer>"
        )
        return f'<symbol type="marker" name="0" alpha="1" clip_to_extent="1">{layer}</symbol>'
    if kind == "line":
        layer = (
            '<layer class="SimpleLine" enabled="1" pass="0" locked="0"><Option type="Map">'
            + _option("line_color", f"{_rgb(outline)},255")
            + _option("line_width", f"{size}")
            + "</Option></layer>"
        )
        return f'<symbol type="line" name="0" alpha="1" clip_to_extent="1">{layer}</symbol>'
    layer = (
        '<layer class="SimpleFill" enabled="1" pass="0" locked="0"><Option type="Map">'
        + _option("color", f"{_rgb(colour)},60" if colour else "0,0,0,0")
        + _option("style", "solid" if colour else "no")
        + _option("outline_color", f"{_rgb(outline)},255")
        + _option("outline_width", f"{size}")
        + "</Option></layer>"
    )
    return f'<symbol type="fill" name="0" alpha="1" clip_to_extent="1">{layer}</symbol>'


def vector(kind: str, colour: str, outline: str, size: float = 0.4, label: str = "") -> str:
    """One symbol for every feature: kind is point, line or polygon; ``label`` a field name."""
    labels = ""
    if label:
        labels = (
            '<labeling type="simple"><settings calloutType="simple">'
            f'<text-style fieldName="{escape(label)}" fontSize="8" textColor="0,0,0,255"/>'
            '<text-buffer bufferDraw="1" bufferSize="0.8" bufferColor="255,255,255,255"/>'
            "</settings></labeling>"
        )
    return (
        f'{HEAD}<qgis version="3.28" styleCategories="Symbology|Labeling">'
        '<renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0">'
        f"<symbols>{_symbol(kind, colour, outline, size)}</symbols></renderer-v2>"
        f"{labels}</qgis>\n"
    )
