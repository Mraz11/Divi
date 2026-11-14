# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The "Trees and canopy" tiles on Make maps."""

import json
from pathlib import Path

from avispria.app.ui.pages.canopy_section import _summary, canopy_tiles, crown_tiles


def test_canopy_and_crown_tiles(tmp_path: Path) -> None:
    tiles = canopy_tiles({"canopy_cover_pct": 70.4, "height_p50_m": 14.2, "tree_tops": 248})
    assert [t.value for t in tiles][:2] == ["70%", "14.2 m"]
    summary = {
        "crowns": {"trees": 247, "structures": 6, "dieback_candidates": 1},
        "sun_elevation_deg": 2.6,
    }
    titles = {t.label: t.value for t in crown_tiles(summary)}
    assert titles == {
        "Trees outlined": "247",
        "Dieback candidates": "1",
        "Sun during the flight": "3 degrees up",
    }
    assert crown_tiles({}) == []
    assert _summary(tmp_path) == {}
    folder = tmp_path / "results" / "canopy"
    folder.mkdir(parents=True)
    (folder / "canopy_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert _summary(tmp_path)["crowns"]["trees"] == 247
