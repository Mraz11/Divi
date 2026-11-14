# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How to cite Dīvi: one line, the same on the screens, in the project record and on reports."""

from __future__ import annotations

from avispria.core.version import __version__

REPOSITORY = "https://github.com/Mraz11/Divi"
REQUEST = "If you publish results made with Dīvi, please cite it."


def citation(version: str = __version__, year: int = 2026) -> str:
    """The reference for this version, until a journal article replaces it."""
    return (
        f"Dīvi contributors ({year}). Dīvi: mapping and measuring forests, farms and towns "
        f"with consumer RGB drones (version {version}) [software]. {REPOSITORY}"
    )
