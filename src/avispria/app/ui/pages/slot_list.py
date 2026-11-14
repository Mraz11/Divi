# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The missions DJI Fly holds on the phone, each with its map picture and when it was made, so
the right one can be chosen without knowing DJI Fly's long file names."""

from __future__ import annotations

import base64
from collections.abc import Callable, Sequence

from nicegui import ui

from avispria.app.phone_workflow import Slot
from avispria.app.ui.views import slot_label


def picture(data: bytes | None) -> None:
    if data:
        encoded = base64.b64encode(data).decode("ascii")
        ui.image(f"data:image/jpeg;base64,{encoded}").classes("w-32 h-24")
    else:
        ui.icon("map").classes("text-5xl av-muted")


def slot_cards(slots: Sequence[Slot], on_use: Callable[[str], object]) -> None:
    """One card per mission, newest first, with "Use as my sample mission" where it can be."""
    for n, slot in enumerate(slots, start=1):
        card = ui.card().props("flat bordered").classes("w-full")
        with card, ui.row().classes("w-full items-center gap-2 no-wrap"):
            picture(slot.preview)
            with ui.column().classes("gap-0 grow"):
                ui.label(f"{n}. Mission {slot.short}...").classes("font-medium")
                ui.label(slot_label(slot)).classes("text-sm av-muted").mark(f"slot-{slot.short}")
            if slot.waypoints > 0:
                ui.button(
                    "Use as my sample mission",
                    on_click=lambda _, g=slot.guid: on_use(g),
                ).props("no-caps outline").mark(f"use-{slot.short}")
            else:
                ui.label(
                    "Dīvi cannot read this mission (it may not be a waypoint mission), so it "
                    "is never replaced."
                ).classes("text-sm av-muted max-w-xs")
