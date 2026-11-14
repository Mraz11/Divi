# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The canopy part of the Make maps results: the numbers a forest study starts from."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nicegui import ui

from avispria.app.ui.views import Tile, explain_issues
from avispria.app.ui.widgets import issue_cards, tile_row
from avispria.core.ground_sources import KIND_TEXT
from avispria.core.safety import Issue

NOTE = (
    "Canopy height is the surface model minus the ground. Where the canopy is closed the ground is "
    "not seen and is interpolated, so measure a few trees in the field before using these numbers "
    "in a study. Fly the same plan again later to measure change."
)


def canopy_tiles(canopy: Mapping[str, Any]) -> list[Tile]:
    """The canopy summary from the provenance record as tiles."""
    ground = KIND_TEXT.get(str(canopy.get("ground_source")), "estimated")
    return [
        Tile(
            "Canopy cover",
            f"{canopy.get('canopy_cover_pct', 0):.0f}%",
            "of the area under trees 2 m and taller",
        ),
        Tile(
            "Canopy height",
            f"{canopy.get('height_p50_m', 0):.1f} m",
            f"median; tallest 5% above {canopy.get('height_p95_m', 0):.1f} m",
        ),
        Tile(
            "Tree tops",
            f"{canopy.get('tree_tops', 0)}",
            f"about {canopy.get('tree_tops_per_ha', 0):.0f} per hectare (a rough crown count)",
        ),
        Tile(
            "Ground seen",
            f"{canopy.get('ground_seen_pct', 0):.0f}%",
            f"of the area ({ground})",
        ),
    ]


def crown_tiles(summary: Mapping[str, Any]) -> list[Tile]:
    """Crowns and the sun from ``canopy_summary.json``."""
    crowns = summary.get("crowns")
    tiles = []
    if isinstance(crowns, Mapping):
        built = crowns.get("structures", 0)
        tiles.append(
            Tile(
                "Trees outlined",
                f"{crowns.get('trees', 0)}",
                f"crowns.geojson opens in QGIS; {built} roofs or other structures left out",
            )
        )
        tiles.append(
            Tile(
                "Dieback candidates",
                f"{crowns.get('dieback_candidates', 0)}",
                "crowns more than half not green: check them on the ground",
            )
        )
    sun = summary.get("sun_elevation_deg")
    if isinstance(sun, int | float):
        tiles.append(
            Tile(
                "Sun during the flight",
                f"{sun:.0f} degrees up",
                "35 or more is good; low sun hides ground and changes colours",
            )
        )
    return tiles


def _t(kg: Mapping[str, Any]) -> str:
    return f"{kg.get('median', 0) / 1000:.1f} t"


def inventory_tiles(inv: Mapping[str, Any]) -> list[Tile]:
    """The tree inventory (``analysis/inventory_summary.json``) as tiles."""
    q = inv.get("quality") or {}
    tiles = [
        Tile(
            "Height model",
            str(q.get("grade", "?")),
            f"{len(q.get('findings') or [])} finding(s) below; ground: "
            f"{KIND_TEXT.get(str((inv.get('ground_choice') or {}).get('kind')), '?')}",
        ),
        Tile(
            "Doming",
            "found" if (q.get("doming") or {}).get("domed") else "-",
            str((q.get("doming") or {}).get("note", "")),
        ),
        Tile(
            "Height correction",
            str((inv.get("height_calibration") or {}).get("method", "none")),
            str((inv.get("height_calibration") or {}).get("note", "")),
        ),
    ]
    b = inv.get("biomass") or {}
    if b.get("trees"):
        agb, co2 = b.get("agb_kg_jucker") or {}, b.get("co2e_kg") or {}
        tiles.append(
            Tile(
                "Biomass above ground",
                _t(agb),
                f"95 % range {_t({'median': agb.get('low', 0)})} to "
                f"{_t({'median': agb.get('high', 0)})}; {b.get('trees')} trees",
            )
        )
        tiles.append(
            Tile(
                "CO2 equivalent",
                _t(co2),
                f"range {_t({'median': co2.get('low', 0)})} to {_t({'median': co2.get('high', 0)})}"
                f"; one tree alone about {b.get('one_tree_band', 0):.1f}x either way",
            )
        )
    s = inv.get("symptoms")
    if isinstance(s, Mapping):
        tiles.append(
            Tile(
                "Visible symptoms",
                f"{s.get('candidates', 0)} crowns",
                f"{s.get('candidate_crown_area_pct', 0):.0f}% of the crown area; to check on the "
                "ground (not latent infection)",
            )
        )
    return tiles


def _summary(out_dir: Path, name: str = "canopy/canopy_summary.json") -> Mapping[str, Any]:
    path = out_dir / "results" / name
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, Mapping) else {}


def show_canopy(provenance: Mapping[str, Any], out_dir: Path) -> None:
    canopy = provenance.get("canopy")
    if not isinstance(canopy, Mapping):
        return
    ui.label("Trees and canopy").classes("text-lg font-bold").mark("canopy-title")
    summary = _summary(out_dir)
    tile_row([*canopy_tiles(canopy), *crown_tiles(summary)])
    preview = out_dir / "results" / "canopy" / "chm_preview.png"
    if preview.is_file():
        ui.image(preview).classes("w-full max-w-xl").props("fit=contain")
        ui.label("Brown: open ground and gaps. Light green to yellow: taller canopy.").classes(
            "text-sm av-muted"
        )
    crown_issues = (summary.get("crowns") or {}).get("issues") or []
    found = [*(canopy.get("issues") or []), *crown_issues]
    issues = [Issue("warning", str(i.get("code", "")), str(i.get("message", ""))) for i in found]
    if issues:
        issue_cards(explain_issues(issues))
    inv = _summary(out_dir, "analysis/inventory_summary.json")
    if inv:
        ui.label("Tree inventory").classes("text-lg font-bold").mark("inventory-title")
        tile_row(inventory_tiles(inv))
        for finding in (inv.get("quality") or {}).get("findings") or []:
            ui.label(f"- {finding}").classes("text-sm")
        b = inv.get("biomass") or {}
        if b.get("limits"):
            ui.label(f"Biomass: {b['limits']}.").classes("text-sm av-muted")
        ui.label(
            "Every tree with its height, biomass range and symptom flag: results/analysis/"
            "trees.csv. Colour indices (relative within this flight): results/analysis/indices/."
        ).classes("text-sm av-muted")
    ui.label(NOTE).classes("text-sm av-muted")
