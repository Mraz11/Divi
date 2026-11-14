# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Report engine: one report per project, saved in its maps folder.

The report (``divi_report.html``) gathers what every engine left on disk: the key numbers with
their ranges, pictures of the maps, the methods written from the records, the quality warnings,
how the maps were made and where the files are, the limits, and how to cite Dīvi. It is one file
with nothing fetched from the internet; printing it from a browser makes the PDF.
"""

from __future__ import annotations

from pathlib import Path

from avispria.app.engines import RECORD_FILE, Links
from avispria.app.report_data import gather
from avispria.app.report_html import render


class ReportError(ValueError):
    """The report cannot be written; the message says why."""


def write_record(
    links: Links, name: str = "", stamps: dict[str, dict[str, str]] | None = None
) -> Path:
    """Write the report into the maps folder and return its path."""
    if not links.maps_folder or not Path(links.maps_folder).is_dir():
        raise ReportError("Make maps first: the report is saved in the maps folder.")
    path = Path(links.maps_folder) / RECORD_FILE
    html = render(gather(links, name, stamps))
    try:
        path.write_text(html, encoding="utf-8")
    except OSError as exc:
        raise ReportError(f"The report could not be written: {exc}") from None
    return path
