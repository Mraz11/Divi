# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Undo, editing a shape by dragging its outline, and full screen, for the drawing map.

Editing: press Edit beside a shape, or click its outline on the map. Handles appear on it: drag
a corner to move it, drag a middle point to add a corner, click a corner to remove it. A circle
has a centre to drag and an edge handle to make it bigger or smaller (or type the radius). Every
finished drag is checked here; one that makes the outline cross itself is refused and the old
outline comes back. A rectangle whose corners are moved becomes a polygon.

Undo goes back one change at a time, whatever it was (a drawing, a role, a delete, a drag), so a
mistake costs one click. Full screen fills the window with the map and its tools; Esc leaves it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import events, ui

from avispria.app.ui.pages.plan_map_full import PAN_HINT, FullScreenMixin
from avispria.core.shapes import DrawnShape, ShapeError, reshape, with_radius

HISTORY_LIMIT = 50

EDIT_CSS = """
.leaflet-draw-section:has(.leaflet-draw-edit-edit) { display: none !important; }
.leaflet-draw-toolbar .leaflet-draw-edit-edit,
.leaflet-draw-toolbar .leaflet-draw-edit-remove { display: none !important; }
.av-map-box { position: relative; width: 100%; }
.av-map-box .av-map { height: clamp(520px, 72vh, 1100px); }
.av-map-bar {
  position: absolute; top: 8px; right: 8px; z-index: 1000; max-width: calc(100% - 70px);
  background: var(--surface); border: 1px solid var(--edge); padding: 2px;
}
.av-map-hint { padding: 0 8px; font-size: 13.5px; }
.av-map-box .leaflet-container.av-panning { cursor: grabbing !important; }
.av-map-box.av-full { position: fixed; inset: 0; z-index: 3000; background: var(--bg); }
.av-map-box.av-full .av-map { height: 100vh !important; }
body:has(.av-full) { overflow: hidden; }
.leaflet-editing-icon { background: var(--surface); border: 2px solid var(--text); }
"""
AREA_HINT = (
    "Editing {name}: drag a corner to move it, drag a middle point to add a corner, "
    "click a corner to remove it."
)
CIRCLE_HINT = (
    "Editing {name}: drag the centre to move it, the handle on the edge to change its size."
)
PICK_HINT = "Click a shape's outline to change it. Right-drag moves the map."


class EditingMixin(FullScreenMixin):
    """Undo, dragging outlines and full screen. Expects the host to have ``shapes``, ``takeoff``,
    ``map``, ``_on_takeoff``, ``_refresh``, ``_forget_layer`` and ``_keep_drawn``."""

    shapes: list[DrawnShape]
    takeoff: tuple[float, float] | None
    map: Any
    _on_takeoff: Callable[[str], None]
    _refresh: Callable[[], None]
    _forget_layer: Callable[[int | None], None]
    _keep_drawn: Callable[[DrawnShape], None]

    def _init_editing(self) -> None:
        self.editing: int | None = None  # the id of the shape whose outline is being edited
        self.full = False
        self._history: list[tuple[tuple[DrawnShape, ...], tuple[float, float] | None]] = []
        self._same_change: tuple[Any, ...] | None = None
        self.undo_button: Any = None
        self.done_button: Any = None
        self.full_button: Any = None
        self.box: Any = None
        self.hint: Any = None

    # ------------------------------------------------------------------------------- undo
    def _remember(self, same_change: tuple[Any, ...] | None = None) -> None:
        """Keep the state as it is now, so Undo can come back to it. Call before a change.

        Typing a number fires a change for every digit; consecutive changes with the same
        ``same_change`` key (the same field of the same shape) are one step to undo, not several.
        """
        if same_change is not None and same_change == self._same_change and self._history:
            return
        self._same_change = same_change
        self._history.append((tuple(self.shapes), self.takeoff))
        del self._history[:-HISTORY_LIMIT]

    def undo(self) -> None:
        if not self._history:
            return
        shapes, takeoff = self._history.pop()
        self._same_change = None
        had = self.takeoff
        self.shapes = list(shapes)
        self.takeoff = takeoff
        if takeoff != had:
            self._on_takeoff("" if takeoff is None else f"{takeoff[1]:.6f}, {takeoff[0]:.6f}")
        if self.editing is not None and self._editing_shape() is None:
            self.editing = None
        self._refresh()

    def _sync_bar(self) -> None:
        """Undo enabled when there is something to undo; Done and the hint while editing."""
        if self.undo_button is not None:
            self.undo_button.set_enabled(bool(self._history))
        shape = self._editing_shape()
        if self.done_button is not None:
            self.done_button.set_visibility(shape is not None)
        if self.hint is not None:
            if shape is not None:
                hint = CIRCLE_HINT if shape.kind == "circle" else AREA_HINT
                self.hint.set_text(hint.format(name=shape.label))
            else:
                self.hint.set_text(PICK_HINT if self.shapes else PAN_HINT)
            self.hint.set_visibility(bool(self.hint.text))

    # ------------------------------------------------------------------------ editing state
    def _editing_shape(self) -> DrawnShape | None:
        return next((s for s in self.shapes if s.id == self.editing), None)

    def start_edit(self, shape_id: int) -> None:
        if self.editing == shape_id:
            return
        self._forget_layer(self.editing)  # the shape edited before loses its handles
        self.editing = shape_id
        self._refresh()

    def done_edit(self) -> None:
        self._forget_layer(self.editing)
        self.editing = None
        self._refresh()

    def _stop_when_drawing(self, _: events.GenericEventArguments) -> None:
        if self.editing is not None:  # a drawing tool was picked: its clicks are not for editing
            self.done_edit()

    def _swap(self, shape: DrawnShape) -> None:
        self.shapes = [shape if s.id == shape.id else s for s in self.shapes]

    # ------------------------------------------------------------------- from the browser
    def _picked(self, e: events.GenericEventArguments) -> None:
        """An outline was clicked on the map: edit that shape."""
        args = e.args if isinstance(e.args, dict) else {}
        if args.get("map") == self.map.id and any(s.id == args.get("shape") for s in self.shapes):
            self.start_edit(int(args["shape"]))

    def _dragged(self, e: events.GenericEventArguments) -> None:
        """A drag on the map ended: keep the new outline, or refuse it and show the old one."""
        args = e.args if isinstance(e.args, dict) else {}
        if args.get("map") != self.map.id:
            return
        shape = next((s for s in self.shapes if s.id == args.get("shape")), None)
        if shape is None:
            return
        try:
            points = tuple((float(lng), float(lat)) for lat, lng in args.get("points") or [])
            radius = args.get("radius")
            new = reshape(shape, points, None if radius is None else float(radius))
        except (ShapeError, TypeError, ValueError) as exc:
            ui.notify(f"That change was not kept: {exc}", type="warning")
            self._forget_layer(shape.id)  # drawn again as it was, with fresh handles
            self._refresh()
            return
        self._remember()
        self._swap(new)
        self._keep_drawn(new)  # the map already shows it
        self._refresh()

    def set_radius(self, value: float | None) -> None:
        shape = self._editing_shape()
        if value is None or shape is None or value == shape.radius_m:
            return
        try:
            new = with_radius(shape, float(value))
        except ShapeError as exc:
            ui.notify(str(exc), type="warning")
            return
        self._remember((shape.id, "radius"))
        self._swap(new)
        self._refresh()

    # --------------------------------------------------------------------------- clicks
    def pick_takeoff(self) -> None:
        """The next click on the map puts the take-off pin there."""
        self.picking_takeoff = True
        ui.notify("Click the map where the drone will take off.", type="info")

    def _map_click(self, e: events.GenericEventArguments) -> None:
        """A click puts the take-off pin (after "Click to set take-off"); otherwise nothing."""
        point = e.args.get("latlng") if isinstance(e.args, dict) else None
        try:
            lat, lon = float(point["lat"]), float(point["lng"])  # type: ignore[index]
        except (KeyError, TypeError, ValueError):
            return
        if getattr(self, "picking_takeoff", False):
            self.picking_takeoff = False
            self._remember()
            self.takeoff = (lon, lat)
            self._on_takeoff(f"{lat:.6f}, {lon:.6f}")
            self._refresh()

    # --------------------------------------------------------------------- the list's part
    def _edit_controls(self, shape: DrawnShape) -> None:
        """Under the shape being edited: how to edit it, the radius of a circle, and Done."""
        with ui.row().classes("w-full items-center gap-2 pl-8"):
            hint = CIRCLE_HINT if shape.kind == "circle" else AREA_HINT
            ui.label(hint.format(name="it")).classes("text-sm")
            if shape.kind == "circle":
                ui.number(
                    "Radius (m)",
                    value=round(shape.radius_m, 1),
                    min=1,
                    max=5000,
                    on_change=lambda e: self.set_radius(e.value),
                ).classes("w-36").mark("edit-radius")
            ui.button("Done", icon="check", on_click=self.done_edit).mark("edit-done-list")
