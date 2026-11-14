# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The "Use a map file" part of the area card: a KML, KMZ, shapefile or GeoJSON, and a buffer.

When a file is chosen, it is read at once and the card says what is in it (how many areas, how
big, which parts of a shapefile were found). The photos can cover exactly the shape or the shape
and a strip around it (the buffer, in metres). "Show it on the map" puts the shapes on the
drawing map, where they can be checked, changed, or one of several areas chosen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nicegui import ui
from shapely.geometry import MultiPolygon, Polygon

from avispria.adapters.area_file import SUFFIXES, AreaFileError, area_from_file
from avispria.app.ui.pages.plan_form_parts import number, show_when
from avispria.app.ui.widgets import PathField
from avispria.core.geometry import LocalFrame

FILE_HINT = (
    "KML or KMZ (Google Earth), a shapefile (.shp, with its .shx, .dbf and .prj in the same "
    "folder, found by themselves; or all of them in one .zip), or GeoJSON."
)
BUFFER_HELP = (
    "Exactly the shape: the flight lines still run a little past its edge, so the edge itself "
    "is photographed as well as the middle. With a buffer, a strip that wide all around the "
    "shape is mapped too."
)


def _hectares(area: Polygon | MultiPolygon) -> str:
    frame = LocalFrame.for_polygon(area.convex_hull)
    pieces = area.geoms if isinstance(area, MultiPolygon) else [area]
    m2 = sum(frame.polygon_to_local(p).area for p in pieces)
    return f"{m2 / 10_000:.2f} ha" if m2 >= 10_000 else f"{m2:,.0f} m²"


class AreaFileSection:
    """Expects ``mode`` (the area radio), ``_open_map`` and ``area_map`` on the host."""

    mode: Any
    area_map: Any
    _open_map: Any

    def _file_section(self) -> None:
        with show_when(self.mode, "file", gap="gap-2"):
            self.aoi_file = PathField(
                "Survey area file",
                directory=False,
                suffixes=SUFFIXES,
                marker="aoi",
                hint=FILE_HINT,
                on_change=self._file_changed,
            )
            self.file_status = ui.label().classes("text-sm").mark("aoi-status")
            self.buffer_kind = (
                ui.radio(
                    {"exact": "Exactly the shape", "buffer": "The shape and a buffer around it"},
                    value="exact",
                    on_change=lambda _: self._file_changed(),
                )
                .props("inline")
                .mark("aoi-buffer-kind")
            )
            with show_when(self.buffer_kind, "buffer", gap="gap-1"):
                self.buffer = number(
                    "Buffer around the shape (m)", 20.0, "aoi-buffer-input", "w-64", min=0, max=5000
                )
                self.buffer.on_value_change(lambda _: self._file_changed())
            ui.label(BUFFER_HELP).classes("text-sm av-muted")
            ui.button("Show it on the map", icon="map", on_click=self._file_to_map).props(
                "outline"
            ).mark("aoi-to-map")

    def buffer_m(self) -> float:
        if self.buffer_kind.value != "buffer":
            return 0.0
        return float(self.buffer.value or 0.0)

    def _read(self) -> tuple[Polygon | MultiPolygon, tuple[str, ...]] | None:
        if not self.aoi_file.value:
            self.file_status.set_text("")
            return None
        try:
            area, found = area_from_file(Path(self.aoi_file.value).expanduser(), self.buffer_m())
        except (AreaFileError, OSError) as exc:
            self.file_status.set_text(f"This file cannot be used: {exc}")
            self.file_status.classes(add="av-problem-text", remove="av-good-text")
            return None
        return area, found.notes

    def _file_changed(self) -> None:
        read = self._read()
        if read is None:
            return
        area, notes = read
        pieces = len(area.geoms) if isinstance(area, MultiPolygon) else 1
        text = f"Area to map: {_hectares(area)}"
        if pieces > 1:
            text += f", in {pieces} separate pieces: show it on the map to choose one"
        self.file_status.set_text("; ".join([text, *notes]))
        self.file_status.classes(add="av-good-text", remove="av-problem-text")

    def _file_to_map(self) -> None:
        read = self._read()
        if read is None:
            ui.notify("Choose a map file with an area in it first.", type="warning")
            return
        area, _notes = read
        self.mode.set_value("drawn")
        self._open_map()
        if self.area_map is not None:
            self.area_map.add_polygons(area.geoms if isinstance(area, MultiPolygon) else [area])
