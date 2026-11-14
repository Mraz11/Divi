# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map images for publication: a layer with a title, legend, north arrow, scale bar and grid.

Drawn with matplotlib on its own canvas (no global plotting state, safe in the background). The
raster is read only at the resolution the image needs, so a 2 cm orthophoto still draws quickly.
PDF and SVG keep text, legend and furniture as vectors; PNG and TIFF are images at the chosen dpi.
"""

from __future__ import annotations

import io
import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import shapely
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle
from pyproj import Transformer
from rasterio.enums import Resampling

from avispria.core.figure_spec import (
    PREVIEW_DPI,
    FigureError,
    FigureSpec,
    auto_height_mm,
    inches,
    length_label,
    nice_length,
    pixels,
)
from avispria.core.landcover import CLASSES
from avispria.core.qml import RAMPS


@dataclass(frozen=True)
class LayerInfo:
    title: str
    source: str  # relative to the results folder
    kind: str  # rgb, continuous or classes
    ramp: str = "grey"
    unit: str = ""
    stretch: tuple[float, float] = (2.0, 98.0)


LAYERS: dict[str, LayerInfo] = {
    "orthophoto": LayerInfo("Orthophoto", "odm_orthophoto/odm_orthophoto.tif", "rgb"),
    "chm": LayerInfo("Canopy height", "canopy/chm.tif", "continuous", "greens", "m", (0.0, 99.0)),
    "dsm": LayerInfo("Surface height (DSM)", "odm_dem/dsm.tif", "continuous", "terrain", "m"),
    "dtm": LayerInfo("Ground height (DTM)", "odm_dem/dtm.tif", "continuous", "terrain", "m"),
    "ground_sigma": LayerInfo(
        "Ground uncertainty (1 sd)", "analysis/ground_sigma.tif", "continuous", "magma", "m"
    ),
    "landcover": LayerInfo("Land cover", "analysis/landcover.tif", "classes"),
    "heat_index": LayerInfo(
        "Heat exposure (relative rank)",
        "analysis/heat/heat_index.tif",
        "continuous",
        "magma",
        "",
        (0.0, 100.0),
    ),
    "sun_hours": LayerInfo(
        "Share of 09-16 h in sun",
        "analysis/heat/sun_hours.tif",
        "continuous",
        "viridis",
        "",
        (0.0, 100.0),
    ),
    "sky_view": LayerInfo(
        "Sky view factor", "analysis/heat/sky_view.tif", "continuous", "grey", "", (0.0, 100.0)
    ),
    "confidence": LayerInfo(
        "Land cover confidence", "analysis/confidence.tif", "continuous", "grey", "%"
    ),
}


def layers(results: Path) -> dict[str, LayerInfo]:
    """The layers this project has, including one per colour index band."""
    found = {k: v for k, v in LAYERS.items() if (results / v.source).is_file()}
    indices = results / "analysis" / "indices"
    for path in sorted(indices.glob("*.tif")) if indices.is_dir() else []:
        found[f"index:{path.stem}"] = LayerInfo(
            f"Colour index {path.stem} (relative within this flight)",
            f"analysis/indices/{path.name}",
            "continuous",
            "diverging",
        )
    return found


def _read(path: Path, kind: str, long_px: int) -> tuple[np.ndarray, Any, Any]:
    """The raster at about ``long_px`` on its long side, its bounds and its CRS."""
    with rasterio.open(path) as src:
        scale = max(1.0, max(src.width, src.height) / max(long_px, 1))
        shape = (max(1, round(src.height / scale)), max(1, round(src.width / scale)))
        method = Resampling.nearest if kind == "classes" else Resampling.average
        if kind == "rgb":
            bands = [1, 2, 3] if src.count >= 3 else [1, 1, 1]
            rgb = src.read(bands, out_shape=(3, *shape), resampling=method)
            alpha = (
                src.read(4, out_shape=shape, resampling=Resampling.nearest)
                if src.count >= 4
                else np.full(shape, 255)
            )
            data = np.dstack([*np.clip(rgb, 0, 255).astype(np.uint8), alpha.astype(np.uint8)])
        else:
            data = src.read(1, out_shape=shape, resampling=method, masked=True).astype(float)
            data = np.ma.masked_invalid(data)
        return data, src.bounds, src.crs


def _cmap(name: str) -> LinearSegmentedColormap:
    ramp = RAMPS[name]
    return LinearSegmentedColormap.from_list(name, [(t, c) for t, c in ramp])


def _range(data: np.ndarray, spec: FigureSpec, info: LayerInfo) -> tuple[float, float]:
    found = np.ma.compressed(data) if np.ma.isMaskedArray(data) else data.ravel()
    found = found[np.isfinite(found)]
    low, high = np.percentile(found, list(info.stretch)) if found.size else (0.0, 1.0)
    low = spec.low if spec.low is not None else float(low)
    high = spec.high if spec.high is not None else float(high)
    return low, max(high, low + 1e-6)


def _north_arrow(ax: Any, size: float) -> None:
    ax.annotate(
        "N",
        xy=(0.94, 0.95),
        xytext=(0.94, 0.80),
        xycoords="axes fraction",
        ha="center",
        va="center",
        fontsize=size * 1.2,
        fontweight="bold",
        arrowprops={"arrowstyle": "-|>", "lw": 1.4, "color": "black"},
        bbox={"boxstyle": "circle,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.8},
    )


def _scale_bar(ax: Any, bounds: Any, size: float) -> None:
    span = bounds.right - bounds.left
    length = nice_length(span)
    height = (bounds.top - bounds.bottom) * 0.012
    x0 = bounds.left + span * 0.04
    y0 = bounds.bottom + (bounds.top - bounds.bottom) * 0.05
    ax.add_patch(
        Rectangle(
            (x0 - span * 0.01, y0 - height * 1.5),
            length + span * 0.02,
            height * 6,
            fc="white",
            ec="none",
            alpha=0.8,
            zorder=4,
        )
    )
    for k in range(2):
        ax.add_patch(
            Rectangle(
                (x0 + k * length / 2, y0),
                length / 2,
                height,
                fc="black" if k == 0 else "white",
                ec="black",
                lw=0.6,
                zorder=5,
            )
        )
    ax.text(
        x0 + length / 2,
        y0 + height * 1.6,
        length_label(length),
        ha="center",
        va="bottom",
        fontsize=size,
        zorder=6,
    )


def _crowns(ax: Any, results: Path, crs: Any) -> None:
    path = results / "canopy" / "crowns.geojson"
    if not path.is_file():
        raise FigureError("There are no tree crowns yet: measure the maps first (step 6).")
    found = json.loads(path.read_text(encoding="utf-8"))
    move = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    for feature in found.get("features", []):
        geom = shapely.geometry.shape(feature["geometry"])
        for part in getattr(geom, "geoms", [geom]):
            xs, ys = move.transform(*part.exterior.xy)
            ax.plot(xs, ys, color="#39ff14", lw=0.5, zorder=3)


def _present(data: np.ndarray, info: LayerInfo) -> list[str]:
    """The names of the land-cover classes in the map (none for other layers)."""
    if info.kind != "classes":
        return []
    found = set(np.unique(np.ma.compressed(data)).astype(int)) - {0}
    return [name for k, (name, _) in CLASSES.items() if k in found]


def _legend(fig: Any, ax: Any, image: Any, data: np.ndarray, info: LayerInfo, size: float) -> None:
    if info.kind == "continuous":
        bar = fig.colorbar(image, ax=ax, shrink=0.8, pad=0.02)
        bar.set_label(f"{info.title}" + (f" ({info.unit})" if info.unit else ""), fontsize=size)
        bar.ax.tick_params(labelsize=size * 0.9)
    elif info.kind == "classes":
        present = _present(data, info)
        handles = [
            Patch(facecolor=np.array(rgb) / 255, edgecolor="black", lw=0.3, label=name)
            for name, rgb in CLASSES.values()
            if name in present
        ]
        ax.legend(
            handles=handles,
            loc="upper left",
            bbox_to_anchor=(1.01, 1),
            fontsize=size * 0.9,
            frameon=False,
            title=info.title,
            title_fontsize=size,
        )


def draw(spec: FigureSpec, results: Path, dpi: int | None = None) -> Figure:
    """The figure for ``spec``; raises FigureError for a choice that cannot be drawn."""
    spec = spec.checked()
    found = layers(results)
    if spec.layer not in found:
        raise FigureError("That layer is not in this project.")
    info = found[spec.layer]
    use_dpi = dpi or spec.dpi
    data, bounds, crs = _read(results / info.source, info.kind, pixels(spec.width_mm, use_dpi))
    ratio = (bounds.top - bounds.bottom) / max(bounds.right - bounds.left, 1e-9)
    size = spec.font_pt
    chars = max(20, int(spec.width_mm / (0.5 * size * 0.3528)))
    caption = textwrap.fill(spec.caption, chars) if spec.caption else ""
    legend = ("bar" if info.kind == "continuous" else "classes") if spec.legend else "none"
    height = spec.height_mm or auto_height_mm(
        spec.width_mm,
        ratio,
        title=bool(spec.title),
        caption_lines=caption.count("\n") + 1 if caption else 0,
        grid=spec.grid,
        legend="none" if info.kind == "rgb" else legend,
        legend_chars=max((len(n) for n in _present(data, info)), default=12),
        font_pt=size,
    )
    fig = Figure(figsize=(inches(spec.width_mm), inches(height)), dpi=use_dpi, layout="constrained")
    ax = fig.add_subplot()
    extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
    if info.kind == "rgb":
        image = ax.imshow(data, extent=extent, interpolation="antialiased")
    elif info.kind == "classes":
        colours = np.array([CLASSES.get(k, ("", (0, 0, 0)))[1] for k in range(max(CLASSES) + 1)])
        cmap = ListedColormap(colours / 255).with_extremes(bad=(0, 0, 0, 0))
        image = ax.imshow(
            np.ma.masked_equal(data, 0),
            extent=extent,
            cmap=cmap,
            vmin=-0.5,
            vmax=max(CLASSES) + 0.5,
            interpolation="nearest",
        )
    else:
        low, high = _range(data, spec, info)
        cmap = _cmap(spec.ramp or info.ramp).with_extremes(bad=(0, 0, 0, 0))
        image = ax.imshow(
            data, extent=extent, cmap=cmap, vmin=low, vmax=high, interpolation="antialiased"
        )
    image.set_rasterized(True)
    if spec.crowns:
        _crowns(ax, results, crs)
    ax.set_xlim(bounds.left, bounds.right)
    ax.set_ylim(bounds.bottom, bounds.top)
    ax.set_aspect("equal")
    if spec.grid:
        ax.ticklabel_format(useOffset=False, style="plain")
        ax.tick_params(labelsize=size * 0.85)
        ax.set_xlabel(f"Easting (m), {crs.to_string() if crs else ''}", fontsize=size * 0.9)
        ax.set_ylabel("Northing (m)", fontsize=size * 0.9)
        ax.grid(True, lw=0.3, color="white", alpha=0.6)
    else:
        ax.set_xticks([])
        ax.set_yticks([])
    if spec.legend:
        _legend(fig, ax, image, data, info, size)
    if spec.north_arrow:
        _north_arrow(ax, size)
    if spec.scale_bar:
        _scale_bar(ax, bounds, size)
    if spec.title:
        fig.suptitle(spec.title, fontsize=size * 1.3, fontweight="bold")
    if caption:
        fig.supxlabel(caption, fontsize=size * 0.9, ha="left", x=0.01)
    return fig


def preview(spec: FigureSpec, results: Path) -> bytes:
    """The same layout at screen resolution, as PNG."""
    fig = draw(spec, results, dpi=PREVIEW_DPI)
    out = io.BytesIO()
    FigureCanvasAgg(fig).print_png(out)
    return out.getvalue()


def save(spec: FigureSpec, results: Path, target: Path) -> Path:
    """Draw at full resolution and save; the format comes from ``spec.fmt``."""
    fig = draw(spec, results)
    target = target.with_suffix(f".{spec.fmt}")
    target.parent.mkdir(parents=True, exist_ok=True)
    FigureCanvasAgg(fig)
    options: dict[str, Any] = {"dpi": spec.dpi, "format": "tiff" if spec.fmt == "tif" else spec.fmt}
    if spec.fmt == "tif":
        options["pil_kwargs"] = {"compression": "tiff_lzw"}
    fig.savefig(target, **options)
    return target
