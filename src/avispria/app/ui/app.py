# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Start the window-based interface: register the screens and run the local web server."""

from __future__ import annotations

import socket

from nicegui import app, ui

from avispria.app.ui.guard import lock_to_this_computer
from avispria.app.ui.layout import ASSETS, MAPS_ONLY, install_look
from avispria.app.ui.pages.after import cut_page, measure_page
from avispria.app.ui.pages.check import check_page
from avispria.app.ui.pages.export import export_page
from avispria.app.ui.pages.figure import figure_page
from avispria.app.ui.pages.fly import fly_page
from avispria.app.ui.pages.home import home_page
from avispria.app.ui.pages.phone import phone_page
from avispria.app.ui.pages.plan import plan_page
from avispria.app.ui.pages.process import process_page
from avispria.app.ui.pages.report import report_page
from avispria.app.ui.state import STATE

HOST = "127.0.0.1"  # this computer only: nothing is reachable from the network


def register_pages(maps_only: bool = False) -> None:
    """Attach every screen to its address. Called once per run (and once per test).

    ``maps_only``: Dīvi Maps, the after-flight program on its own: making maps is its first
    screen and the flight-planning screens are not there.
    """
    install_look()
    MAPS_ONLY["on"] = maps_only
    app.add_static_files("/assets", ASSETS)  # the logo, the page icon, the font and the icons
    ui.page("/process")(process_page)
    ui.page("/map")(cut_page)
    ui.page("/analyse")(measure_page)
    ui.page("/export")(export_page)
    ui.page("/figure")(figure_page)
    ui.page("/report")(report_page)
    if maps_only:
        ui.page("/")(process_page)
        return
    ui.page("/")(home_page)
    ui.page("/check")(check_page)
    ui.page("/plan")(plan_page)
    ui.page("/phone")(phone_page)
    ui.page("/fly")(fly_page)


def find_free_port(start: int, tries: int = 20) -> int:
    """``start`` if it is free, else the next free port above it."""
    for port in range(start, start + tries):
        with socket.socket() as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
            return port
    raise OSError(f"no free port between {start} and {start + tries - 1}")


def run_app(port: int = 8080, open_browser: bool = True, maps_only: bool = False) -> None:
    STATE.load()  # remember the sample mission, the phone settings and the last plan between runs
    register_pages(maps_only)
    port = find_free_port(port)
    lock_to_this_computer(port)
    ui.run(
        host=HOST,
        port=port,
        show=open_browser,
        reload=False,
        title="Dīvi Maps" if maps_only else "Dīvi",
        favicon=ASSETS / "favicon.png",
    )
