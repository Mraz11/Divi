# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which analyses to run: one switch each, remembered between runs."""

from __future__ import annotations

from nicegui import ui

from avispria.app.ui.state import STATE
from avispria.core.analyses import SWITCHES

ALWAYS = (
    "Always done: the canopy height model with its quality checks, and the tree tops and crowns. "
    "Switch off what you do not need: it is not computed, saved or reported, and you can do it "
    "in QGIS or another program from the exported files instead."
)


class SwitchSection:
    """A switch per analysis; ``off()`` is what was switched off."""

    def __init__(self, opened: bool = False) -> None:
        self.switches: dict[str, ui.switch] = {}
        with (
            ui.expansion("What to measure", icon="tune", value=opened)
            .classes("w-full border")
            .mark("analysis-switches"),
            ui.column().classes("w-full gap-2 p-2"),
        ):
            ui.label(ALWAYS).classes("text-sm av-muted")
            for item in SWITCHES:
                with ui.row().classes("w-full items-start gap-2 no-wrap"):
                    self.switches[item.key] = (
                        ui.switch(value=item.key not in STATE.analyses_off)
                        .mark(f"switch-{item.key}")
                        .on_value_change(self._remember)
                    )
                    with ui.column().classes("gap-0"):
                        ui.label(item.title).classes("font-medium")
                        ui.label(item.what).classes("text-sm av-muted")

    def off(self) -> tuple[str, ...]:
        return tuple(key for key, switch in self.switches.items() if not switch.value)

    def _remember(self) -> None:
        STATE.analyses_off = list(self.off())
