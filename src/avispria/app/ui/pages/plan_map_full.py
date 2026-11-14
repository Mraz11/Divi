# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Full screen and panning for every map that is drawn on (the area map and the pin map).

Full screen fills the window with the map and its tools; Esc or the same button leaves it. The
right mouse button drags the map, so the left one only draws: while a drawing tool is on, a left
click always puts a point, even if the hand moves a little (on a touch screen one finger still
moves the map, as there is no right button).
"""

from __future__ import annotations

from typing import Any

from nicegui import events, ui

PAN_HINT = "Right-drag to move the map, wheel to zoom."


class FullScreenMixin:
    """Expects ``map``, ``box`` (the div around the map) and ``full_button`` on the host."""

    map: Any
    box: Any
    full_button: Any
    full: bool

    def _full_button(self) -> Any:
        self.full = False
        self.full_button = (
            ui.button("Full screen", icon="fullscreen", on_click=self.toggle_full)
            .props("outline")
            .mark("map-full")
        )
        return self.full_button

    def _map_ready(self) -> None:
        """Right-drag panning, and Esc to leave full screen. Call once the map is built."""
        ui.keyboard(on_key=self._key, ignore=["input", "select", "textarea"])
        self.map.client.run_javascript(f"diviMap.pan({self.map.id!r})")

    def set_full(self, full: bool) -> None:
        self.full = full
        if self.box is not None:
            if full:
                self.box.classes(add="av-full")
            else:
                self.box.classes(remove="av-full")
        if self.full_button is not None:
            self.full_button.set_text("Exit full screen" if full else "Full screen")
            self.full_button.props(f"icon={'fullscreen_exit' if full else 'fullscreen'}")
        self.map.client.run_javascript(f"diviMap.resize({self.map.id!r})")

    def toggle_full(self) -> None:
        self.set_full(not self.full)

    def _key(self, e: events.KeyEventArguments) -> None:
        if self.full and e.key.escape and e.action.keydown:
            self.set_full(False)
