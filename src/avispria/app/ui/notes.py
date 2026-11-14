# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Short messages shown from event handlers, tied to the element the event came from.

From NiceGUI 4, a message needs to know which page it belongs to, and an event handler (a map
click, a drawn shape) may run without that context. ``notify_at`` takes it from the element.
"""

from __future__ import annotations

from typing import Literal

from nicegui import ui

Kind = Literal["positive", "negative", "warning", "info", "ongoing"]


def notify_at(anchor: ui.element, text: str, kind: Kind = "warning") -> None:
    """Show ``text`` on the page that holds ``anchor``."""
    with anchor:
        ui.notify(text, type=kind)
