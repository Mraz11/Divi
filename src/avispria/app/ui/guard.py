# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Keep the local server to this computer and to Dīvi's own pages.

The server listens on 127.0.0.1 only, so nothing on the network can reach it. Two more doors are
closed here, both against a website open in the same browser:

* DNS rebinding: a site can make its own address point at 127.0.0.1 and then read Dīvi's pages
  as if they were its own. Every request whose Host is not 127.0.0.1 or localhost is refused.
* Cross-site connections: the live connection behind every screen (socket.io) accepts only the
  page Dīvi itself served, never another site's.
"""

from __future__ import annotations

from nicegui import app, core
from starlette.middleware.trustedhost import TrustedHostMiddleware

ALLOWED_HOSTS = ("127.0.0.1", "localhost")


def origins(port: int) -> list[str]:
    return [f"http://{host}:{port}" for host in ALLOWED_HOSTS]


def lock_to_this_computer(port: int) -> None:
    """Call once, before the server starts."""
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(ALLOWED_HOSTS))
    core.sio.eio.cors_allowed_origins = origins(port)
