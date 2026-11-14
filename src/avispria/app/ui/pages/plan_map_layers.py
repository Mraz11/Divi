# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the drawing map shows, and the handles to drag a shape's outline (``AreaMap`` uses this).

Only what changed is redrawn: a shape keeps its map layer until it is changed or removed, so
drawing a new shape does not make the others flicker. The area that will be planned (green) is
redrawn only when it changes, and lets clicks through to the outlines below it.

Editing is done on the map itself. The browser part (``MAP_JS``) turns on Leaflet.draw's own
handles on the outline being edited: drag a corner to move it, drag a middle point to add a
corner, click a corner to remove it; a circle has a centre to drag and an edge handle for its
size. Each finished drag is sent here as the new outline (``divi_shape_edit``), checked, and kept
or refused; the server stays the owner of every shape. A click on any outline picks that shape
for editing (``divi_shape_pick``).
"""

from __future__ import annotations

import json
from typing import Any

from avispria.app.ui.pages.plan_map_text import ROLE_COLOURS
from avispria.core.shapes import AreaResult, DrawnShape

PLANNED_COLOUR = "#1B766B"
PLANNED_FILL = "#2D9A5B"

MAP_JS = """
window.diviMap = window.diviMap || {
  find(mapId, layerId, then, tries = 0) {
    const el = getElement(mapId);
    let found = null;
    if (el && el.map) el.map.eachLayer((l) => { if (l.id === layerId) found = l; });
    if (found) return then(found);
    if (tries < 80) setTimeout(() => this.find(mapId, layerId, then, tries + 1), 50);
  },
  shape(mapId, layerId, shapeId) {
    this.find(mapId, layerId, (layer) => {
      if (layer._diviShape) return;
      layer._diviShape = shapeId;
      layer.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        emitEvent("divi_shape_pick", { map: mapId, shape: shapeId });
      });
    });
  },
  edit(mapId, layerId, shapeId) {
    this.find(mapId, layerId, (layer) => {
      if (!layer.editing) return;
      layer.editing.enable();
      if (layer._diviEdit) return;
      layer._diviEdit = true;
      layer.on("edit", () => {
        let points, radius = null;
        if (layer instanceof L.Circle) {
          const c = layer.getLatLng();
          points = [[c.lat, c.lng]];
          radius = layer.getRadius();
        } else {
          let ll = layer.getLatLngs();
          while (Array.isArray(ll[0])) ll = ll[0];
          points = ll.map((p) => [p.lat, p.lng]);
        }
        emitEvent("divi_shape_edit", { map: mapId, shape: shapeId, points, radius });
      });
    });
  },
  pan(mapId, tries = 0) {
    const el = getElement(mapId);
    if (!el || !el.map) {
      if (tries < 80) setTimeout(() => this.pan(mapId, tries + 1), 50);
      return;
    }
    const map = el.map;
    if (map._diviPan) return;
    map._diviPan = true;
    const box = map.getContainer();
    let last = null;
    const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
    box.addEventListener("contextmenu", (e) => e.preventDefault());
    box.addEventListener("mousedown", (e) => {
      if (e.button !== 2) return;
      last = [e.clientX, e.clientY];
      box.classList.add("av-panning");
      stop(e);
    }, true);
    const end = () => {
      if (!last) return;
      last = null;
      box.classList.remove("av-panning");
    };
    // the release is caught first, on the window, wherever the pointer is: so the drag always
    // ends, and the drawing tools never take the right button's release for a click
    window.addEventListener("mouseup", (e) => {
      if (e.button !== 2) return;
      if (last) stop(e);
      end();
    }, true);
    window.addEventListener("mousemove", (e) => {
      if (!last) return;
      if ((e.buttons & 2) === 0) return end();  // released outside the window, or missed
      map.panBy([last[0] - e.clientX, last[1] - e.clientY], { animate: false });
      last = [e.clientX, e.clientY];
    });
    window.addEventListener("blur", end);
    document.addEventListener("visibilitychange", end);
    // while a drawing tool is on, the left button only draws (a mouse, not a finger)
    const mouse = window.matchMedia && window.matchMedia("(pointer: fine)").matches;
    map.on("draw:drawstart", () => { if (mouse) map.dragging.disable(); });
    map.on("draw:drawstop", () => map.dragging.enable());
  },
  fit(mapId, bounds, tries = 0) {
    const el = getElement(mapId);
    if (!el || !el.map || !el.map.getContainer().offsetHeight) {
      if (tries < 80) setTimeout(() => this.fit(mapId, bounds, tries + 1), 50);
      return;
    }
    el.map.invalidateSize();
    el.map.fitBounds(bounds, { padding: [30, 30], animate: false });
  },
  resize(mapId) {
    setTimeout(() => {
      const el = getElement(mapId);
      if (el && el.map) el.map.invalidateSize();
    }, 60);
  },
};
"""


def latlngs(points: tuple[tuple[float, float], ...]) -> list[list[float]]:
    return [[lat, lon] for lon, lat in points]


class LayersMixin:
    """The map's layers. Expects ``map``, ``shapes``, ``result``, ``chosen``, ``takeoff`` and
    ``editing`` on the host."""

    map: Any
    shapes: list[DrawnShape]
    result: AreaResult | None
    chosen: int
    takeoff: tuple[float, float] | None
    editing: int | None

    def _init_layers(self) -> None:
        self._shape_layers: dict[int, tuple[DrawnShape, Any]] = {}
        self._result_layers: list[Any] = []
        self._result_key: Any = None
        self._takeoff_layer: Any = None
        self._takeoff_drawn: tuple[float, float] | None = None
        self._editing_layer: Any = None  # the layer whose handles are on

    def _js(self, code: str) -> None:
        self.map.client.run_javascript(code)

    def _call(self, name: str, *args: Any) -> None:
        self._js(f"diviMap.{name}({', '.join(json.dumps(a) for a in args)})")

    # ----------------------------------------------------------------------------- shapes
    def _shape_layer(self, shape: DrawnShape) -> Any:
        style = {"color": ROLE_COLOURS[shape.role], "weight": 3, "dashArray": "6", "fill": False}
        if shape.kind == "circle":
            centre = latlngs(shape.points)[0]
            return self.map.generic_layer(
                name="circle", args=[centre, {**style, "radius": shape.radius_m}]
            )
        if shape.kind == "line":
            return self.map.generic_layer(name="polyline", args=[latlngs(shape.points), style])
        return self.map.generic_layer(name="polygon", args=[latlngs(shape.points), style])

    def _forget_layer(self, shape_id: int | None) -> None:
        """Take a shape's layer off the map, so the next redraw draws it afresh (no handles)."""
        drawn = self._shape_layers.pop(shape_id, None) if shape_id is not None else None
        if drawn is not None:
            self.map.remove_layer(drawn[1])
            if drawn[1] is self._editing_layer:
                self._editing_layer = None

    def _keep_drawn(self, shape: DrawnShape) -> None:
        """The map already shows ``shape`` (it was dragged there): do not draw it again."""
        drawn = self._shape_layers.get(shape.id)
        if drawn is not None:
            self._shape_layers[shape.id] = (shape, drawn[1])

    def _redraw_map(self) -> None:
        wanted = {s.id: s for s in self.shapes}
        for shape_id, (drawn, _layer) in list(self._shape_layers.items()):
            if wanted.get(shape_id) != drawn:
                self._forget_layer(shape_id)
        for shape in self.shapes:
            if shape.id not in self._shape_layers:
                layer = self._shape_layer(shape)
                self._shape_layers[shape.id] = (shape, layer)
                self._call("shape", self.map.id, layer.id, shape.id)
        drawn = self._shape_layers.get(self.editing) if self.editing is not None else None
        if drawn is None:
            self._editing_layer = None
        elif drawn[1] is not self._editing_layer:
            self._editing_layer = drawn[1]
            self._call("edit", self.map.id, drawn[1].id, drawn[0].id)
        self._redraw_result()
        self._redraw_takeoff()

    # ----------------------------------------------------------------------- the result
    def _redraw_result(self) -> None:
        pieces = self.result.pieces if self.result is not None else ()
        key = (tuple(p.polygon.wkb for p in pieces), self.chosen)
        if key == self._result_key:
            return
        self._result_key = key
        for layer in self._result_layers:
            self.map.remove_layer(layer)
        self._result_layers = []
        for n, piece in enumerate(pieces):
            rings = [
                list(piece.polygon.exterior.coords),
                *(list(r.coords) for r in piece.polygon.interiors),
            ]
            here = n == self.chosen
            style = {
                "color": PLANNED_COLOUR,
                "weight": 3 if here else 1,
                "fillColor": PLANNED_FILL,
                "fillOpacity": 0.3 if here else 0.12,
                "interactive": False,  # clicks go through to the outlines underneath
            }
            rings_latlng = [[[lat, lon] for lon, lat in ring] for ring in rings]
            self._result_layers.append(
                self.map.generic_layer(name="polygon", args=[rings_latlng, style])
            )

    def _redraw_takeoff(self) -> None:
        if self.takeoff == self._takeoff_drawn and (
            self.takeoff is None or self._takeoff_layer is not None
        ):
            return
        if self._takeoff_layer is not None:
            self.map.remove_layer(self._takeoff_layer)
            self._takeoff_layer = None
        if self.takeoff is not None:
            self._takeoff_layer = self.map.marker(latlng=(self.takeoff[1], self.takeoff[0]))
        self._takeoff_drawn = self.takeoff
