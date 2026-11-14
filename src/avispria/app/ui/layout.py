# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The frame around every screen: header with logo and navigation, content, footer.

The look is a precise survey instrument: Archivo for text and JetBrains Mono for data, 1px edges,
gently rounded corners, no shadows (``assets/avispria.css``), Lucide outline icons (``icons.py``),
and Quasar's controls made compact and flat by default (``install_look``). The top bar draws the
pipeline as a flight line with one waypoint per step (``transect``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from nicegui import app, ui

from avispria.app.ui import projects
from avispria.app.ui.icons import icon_map_js
from avispria.app.ui.journey import journey_bar, nav_items, next_step_card, step_for
from avispria.app.ui.theme import THEME_BOOT_JS, tokens_css
from avispria.app.ui.theme_state import ThemeState, attach
from avispria.core.version import __version__

ASSETS = Path(__file__).parent / "assets"
COMPONENT_CSS = (ASSETS / "avispria.css").read_text(encoding="utf-8")
BRAND = "Dīvi"  # दीवि: Dī (intellect) + Vi (the bird); Magadhi Prakrit, mother of Bengali
TAGLINE = "Fly. Analyze. Decide."
PURPOSE = "Maps and measurements of forests, farms and towns from an ordinary drone."

NAV = nav_items()  # Start, then the engines of the pipeline in the order they are done
NAV_STATE = {"done": " av-nav-done", "partial": " av-nav-partial"}
# "Dīvi Maps": the after-flight program on its own (``divi maps``), with no flight-planning
# screens and no navigation to them
MAPS_ONLY = {"on": False}


def install_look() -> None:
    """Flat, square, compact Quasar controls everywhere, and the outline icons. Safe to repeat."""
    ui.button.default_props("unelevated square")
    for field in (ui.input, ui.number, ui.select, ui.textarea):
        field.default_props("outlined dense square stack-label")
    ui.card.default_props("flat square bordered")
    ui.expansion.default_props("dense")
    ui.table.default_props("flat bordered dense square separator=cell")
    ui.chip.default_props("square dense")
    script = icon_map_js()
    if script not in app.config.vue_config_script:  # before Quasar starts: see icons.py
        app.config.vue_config_script = script + app.config.vue_config_script


def themed_css() -> str:
    """The colour variables and component styles, inside NiceGUI's ``overrides`` layer.

    NiceGUI loads Quasar's ``!important`` rules (``text-white`` on coloured buttons,
    ``text-primary``) in a layer of their own, and a layered ``!important`` beats an unlayered one
    whatever its specificity. The ``overrides`` layer is declared before Quasar's important layer,
    so here our ``!important`` rules win, as they must for labels to keep their contrast.
    """
    return "@layer overrides {\n" + tokens_css(quasar=True) + COMPONENT_CSS + "\n}\n"


def logo(classes: str = "") -> None:
    """The logo: the original colours on light pages, the dark-mode variant on dark ones."""
    ui.element("img").props(f'src="/assets/logo.png" alt="{BRAND} logo"').classes(
        f"av-logo av-logo-light {classes}"
    ).mark("logo-light")
    ui.element("img").props('src="/assets/logo-dark.png" alt=""').classes(
        f"av-logo av-logo-dark {classes}"
    ).mark("logo-dark")


def _theme_button(state: ThemeState) -> None:
    button = (
        ui.button(icon="dark_mode", on_click=state.toggle)
        .props('flat dense aria-label="Switch between light and dark mode"')
        .classes("av-theme")
        .mark("theme-toggle")
    )
    button.tooltip("Light or dark")

    def show_icon(_palette: object) -> None:
        button.props(f"icon={'light_mode' if state.dark else 'dark_mode'}")
        button.update()

    state.on_change(show_icon)


def last_reached(keys: list[str], done: set[str]) -> int:
    """The position of the last finished step on the flight line (0, Start, if none)."""
    reached = [n for n, key in enumerate(keys) if key in done]
    return reached[-1] if reached else 0


def transect(title: str, engine: str, maps_only: bool) -> None:
    """The top bar's flight line: Start, then a waypoint per engine, green as far as it is done."""
    status = {s.spec.key: s.status for s in projects.states()}
    items = nav_items(maps_only)
    keys = [key for _, _, key in items]
    tip = last_reached(keys, {key for key, value in status.items() if value == "done"})
    with (
        ui.element("nav")
        .classes("av-transect")
        .props('aria-label="Steps of the project"')
        .mark("transect")
    ):
        for n, (name, path, key) in enumerate(items):
            here = key == engine if engine else name == title
            link = ui.link(name, path).classes(
                "av-nav"
                + (" av-nav-start" if key == "" else "")
                + (" av-nav-active" if here else "")
                + (" av-nav-reached" if n < tip else " av-nav-tip" if n == tip and tip else "")
                + NAV_STATE.get(status.get(key, ""), "")
            )
            if here:
                link.props('aria-current="page"')


@contextmanager
def frame(title: str) -> Iterator[None]:
    ui.page_title(f"{title} - {BRAND}")
    ui.add_head_html(f"<script>{THEME_BOOT_JS}</script>")  # the right colours from the first paint
    ui.add_css(themed_css())
    ui.add_head_html('<link rel="stylesheet" href="/assets/icons.css">')
    state = ThemeState(ui.dark_mode(False))
    attach(state)
    ui.on("avispria_theme", lambda event: state.from_browser(event.args))
    ui.context.client.on_connect(
        lambda: ui.run_javascript(
            "emitEvent('avispria_theme', document.documentElement.getAttribute('data-theme'))"
        )
    )
    with ui.header().classes("items-stretch gap-0 no-wrap"):
        with ui.link(target="/").classes("av-brand av-cell no-wrap"):
            logo()
            ui.label(BRAND).classes("av-brand-name")
        maps_only = MAPS_ONLY["on"]
        ui.label("Maps: after the flight" if maps_only else TAGLINE).classes(
            "av-tagline av-cell gt-sm"
        )
        ui.space()
        step = step_for(title)
        transect(title, step.engine if step is not None else "", maps_only)
        _theme_button(state)
    with ui.column().classes("w-full max-w-6xl mx-auto p-3 gap-4 pb-10"):
        ui.label(title).classes("av-title")
        if step is not None:
            journey_bar(step, maps_only)
        yield
        if step is not None:
            next_step_card(step, maps_only)
    with ui.footer().classes("justify-between text-xs"):
        ui.label(
            f"{BRAND} {__version__} - early version, not yet flight-tested. "
            "You are responsible for every flight; check local rules."
        )
