# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The map-image screen's rules, without a browser: what the form holds becomes a FigureSpec."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path

from avispria.app.figure import layers, preview, save
from avispria.app.ui.after_job import AfterError, maps_folder
from avispria.core.figure_spec import WIDTHS_MM, FigureError, FigureSpec, pixels

CUSTOM = "Custom width"
FIGURES_DIR = "export/figures"


@dataclass(frozen=True)
class FigureForm:
    folder: str
    layer: str
    width_choice: str
    custom_width_mm: float | None
    auto_height: bool
    height_mm: float | None
    dpi: int
    fmt: str
    title: str = ""
    caption: str = ""
    legend: bool = True
    north_arrow: bool = True
    scale_bar: bool = True
    grid: bool = True
    crowns: bool = False
    ramp: str = ""
    low: float | None = None
    high: float | None = None
    font_pt: float = 8.0

    def spec(self) -> FigureSpec:
        width = WIDTHS_MM.get(self.width_choice, self.custom_width_mm)
        if width is None:
            raise FigureError("Give the width in millimetres.")
        if not self.auto_height and self.height_mm is None:
            raise FigureError("Give the height in millimetres, or let it fit the map.")
        return FigureSpec(
            layer=self.layer,
            width_mm=float(width),
            height_mm=None if self.auto_height else self.height_mm,
            dpi=int(self.dpi),
            title=self.title.strip(),
            caption=self.caption.strip(),
            legend=self.legend,
            north_arrow=self.north_arrow,
            scale_bar=self.scale_bar,
            grid=self.grid,
            crowns=self.crowns,
            ramp=self.ramp,
            low=self.low,
            high=self.high,
            font_pt=float(self.font_pt),
            fmt=self.fmt,
        ).checked()


def layer_choices(folder_text: str) -> dict[str, str]:
    """{key: title} of the layers in a maps folder; empty when there are none."""
    try:
        folder = maps_folder(folder_text)
    except AfterError:
        return {}
    return {key: info.title for key, info in layers(folder / "results").items()}


def size_text(form: FigureForm) -> str:
    """'170 x auto mm at 300 dpi = 2008 px wide' for the screen."""
    try:
        spec = form.spec()
    except FigureError:
        return ""
    tall = "fits the map" if spec.height_mm is None else f"{spec.height_mm:g} mm"
    return (
        f"{spec.width_mm:g} mm wide, height {tall}; {spec.dpi} dpi = "
        f"{pixels(spec.width_mm, spec.dpi)} pixels wide"
    )


def preview_job(form: FigureForm) -> str:
    """The preview as a data URL for an image on the screen; raises AfterError."""
    folder = maps_folder(form.folder)
    try:
        png = preview(form.spec(), folder / "results")
    except FigureError as exc:
        raise AfterError(str(exc)) from None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def file_name(form: FigureForm) -> str:
    base = form.title.strip() or form.layer.replace("index:", "index_")
    cleaned = re.sub(r"[^\w\-]+", "_", base, flags=re.UNICODE).strip("_")[:60] or "map"
    return cleaned


def save_job(form: FigureForm) -> Path:
    """Save the image in ``export/figures`` of the maps folder; an older one is not overwritten."""
    folder = maps_folder(form.folder)
    try:
        spec = form.spec()
    except FigureError as exc:
        raise AfterError(str(exc)) from None
    target_dir = folder / FIGURES_DIR
    name = file_name(form)
    target = target_dir / f"{name}.{spec.fmt}"
    n = 2
    while target.exists():
        target = target_dir / f"{name}-{n}.{spec.fmt}"
        n += 1
    try:
        return save(spec, folder / "results", target)
    except FigureError as exc:
        raise AfterError(str(exc)) from None
