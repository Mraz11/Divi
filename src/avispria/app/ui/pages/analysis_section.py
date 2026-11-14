# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The analysis part of the Make maps results: land cover and what it adds up to."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nicegui import ui

from avispria.app.ui.views import Tile, explain_issues
from avispria.app.ui.widgets import issue_cards, tile_row
from avispria.core.landcover import CLASSES
from avispria.core.safety import Issue

TITLES = {"forest": "Your forest", "farm": "Your farm", "urban": "Your town"}


def read_summary(out_dir: Path) -> Mapping[str, Any]:
    path = out_dir / "results" / "analysis" / "surface_summary.json"
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, Mapping) else {}


def analysis_tiles(m: Mapping[str, Any]) -> list[Tile]:
    tiles = [Tile("Tree canopy", f"{m.get('tree_canopy_pct', 0):.0f}%", "of the area")]
    if "green_pct" in m:  # land cover on
        tiles.append(
            Tile(
                "All green",
                f"{m.get('green_pct', 0):.0f}%",
                "trees, shrubs, grass, crops and green roofs",
            )
        )
        tiles.append(
            Tile("Sealed", f"{m.get('impervious_pct', 0):.0f}%", "roofs, paving and vehicles")
        )
    if m.get("buildings"):
        tiles.append(
            Tile(
                "Buildings",
                f"{m['buildings']}",
                f"{m.get('built_area_m2', 0):.0f} m2 of roof; rooftop vegetation "
                f"{m.get('rooftop_green_m2', 0):.0f} m2",
            )
        )
    if m.get("roads"):
        tiles.append(
            Tile(
                "Street trees",
                f"{m.get('street_trees', 0)}",
                f"{m.get('street_trees_per_100m', 0):.1f} per 100 m of road; "
                f"{m.get('street_tree_gaps', 0)} planting gap(s)",
            )
        )
    if m.get("street_shade_pct") is not None:
        tiles.append(
            Tile(
                "Street shade", f"{m['street_shade_pct']:.0f}%", "of roads shaded by trees at 14:00"
            )
        )
    if "confidence_mean" in m:
        tiles.append(
            Tile(
                "Confidence",
                f"{m.get('confidence_mean', 0):.0f} / 100",
                "how sure the land cover is (confidence.tif shows where)",
            )
        )
    return tiles


def show_analysis(out_dir: Path) -> None:
    summary = read_summary(out_dir)
    metrics = summary.get("metrics")
    if not isinstance(metrics, Mapping):
        return
    title = TITLES.get(str(summary.get("profile")), "Your map")
    ui.label(title).classes("text-lg font-bold").mark("analysis-title")
    tile_row(analysis_tiles(metrics))
    preview = out_dir / "results" / "analysis" / "landcover_preview.png"
    if preview.is_file():
        ui.image(preview).classes("w-full max-w-xl").props("fit=contain")
        present = metrics.get("cover_pct") or {}
        with ui.row().classes("gap-2 flex-wrap").mark("landcover-legend"):
            for name, colour in CLASSES.values():
                if name in present:
                    with ui.row().classes("items-center gap-1"):
                        r, g, b = colour
                        ui.element("div").style(
                            f"width:14px;height:14px;border-radius:3px;background:rgb({r},{g},{b})"
                        )
                        ui.label(f"{name} {present[name]:.0f}%").classes("text-sm")
    found = summary.get("issues") or []
    issues = [Issue("warning", str(i.get("code", "")), str(i.get("message", ""))) for i in found]
    if issues:
        issue_cards(explain_issues(issues))
    ui.label(
        "Land cover is worked out from height, roughness and colour, with shadows predicted from "
        "the 3D model and the sun. Check a sample of it against the orthophoto before using the "
        "numbers; the files in results/analysis open in QGIS."
    ).classes("text-sm av-muted")
