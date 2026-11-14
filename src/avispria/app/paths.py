# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dīvi's folder in the user's home: settings, phone backups, sample missions, adb tools.

The project was called Avispria, and so was this folder (``~/Avispria``). New installs use
``~/Divi`` (plain letters: some tools mishandle accents in paths). An existing ``~/Avispria``
that holds Dīvi's own data keeps being used, and is never moved or renamed: the same name is
also a common place for the program's source code (``git clone`` makes ``~/Avispria``), and
moving that would break it.
"""

from __future__ import annotations

from pathlib import Path

HOME_NAME = "Divi"
OLD_HOME_NAME = "Avispria"


PROVENANCE = "divi_provenance.json"
OLD_PROVENANCE = "avispria_provenance.json"  # written before the rename


def provenance_file(out_dir: Path) -> Path:
    """The provenance record of a results folder: the new name, or the old one if only it exists."""
    new, old = out_dir / PROVENANCE, out_dir / OLD_PROVENANCE
    return old if not new.exists() and old.exists() else new


# What Dīvi itself writes there; a folder with none of these is not Dīvi's data folder.
APP_ENTRIES = ("settings.json", "phone-backups", "phone-samples", "platform-tools")
# A folder with any of these is a copy of the source code, never the data folder.
SOURCE_MARKERS = (".git", "pyproject.toml")


def is_old_data_folder(folder: Path) -> bool:
    """Whether ``folder`` is the data folder written before the rename (not a source checkout)."""
    if not folder.is_dir() or any((folder / m).exists() for m in SOURCE_MARKERS):
        return False
    return any((folder / e).exists() for e in APP_ENTRIES)


def app_home(home: Path | None = None) -> Path:
    """``~/Divi``, or the old ``~/Avispria`` data folder if only that one exists. Moves nothing."""
    base = Path.home() if home is None else home
    new, old = base / HOME_NAME, base / OLD_HOME_NAME
    if not new.exists() and is_old_data_folder(old):
        return old
    return new
