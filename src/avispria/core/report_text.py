# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The words of the report: numbers with their ranges, the methods paragraph, the references.

Everything here is written from the records the engines left on disk (the provenance record and
the canopy, surface and inventory summaries), read as plain dictionaries. A key that is missing
leaves its sentence out; nothing is guessed. Every function is pure and tested on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

Record = Mapping[str, Any]
DASH = "–"  # en dash, for ranges
LIMITS = (
    "Heights, cover and biomass are estimates from photographs. Report each number with its "
    "range or quality grade.",
    "Colour indices are relative within one flight. They are not comparable between flights "
    "without the rank method, and they do not measure plant health directly.",
    "Disease is reported only as visible symptoms at crown or plot scale.",
    "This version of Dīvi has not been validated against field measurements. Check a sample "
    "against the ground before using the numbers.",
)


@dataclass(frozen=True)
class Reference:
    key: str
    text: str


REFERENCES: dict[str, Reference] = {
    r.key: r
    for r in (
        Reference(
            "odm",
            "OpenDroneMap Authors. ODM: a command line toolkit to generate maps, point clouds, "
            "3D models and DEMs from drone, balloon or kite images. https://github.com/"
            "OpenDroneMap/ODM",
        ),
        Reference(
            "jucker",
            "Jucker, T. et al. (2017). Allometric equations for integrating remote sensing "
            "imagery into forest monitoring programmes. Global Change Biology 23: 177–190.",
        ),
        Reference(
            "chave",
            "Chave, J. et al. (2014). Improved allometric models to estimate the aboveground "
            "biomass of tropical trees. Global Change Biology 20: 3177–3190.",
        ),
        Reference(
            "ipcc",
            "IPCC (2006). 2006 IPCC Guidelines for National Greenhouse Gas Inventories, Vol. 4, "
            "Ch. 4 (carbon fraction of dry matter 0.47).",
        ),
        Reference(
            "deepforest",
            "Weinstein, B. G. et al. (2020). DeepForest: a Python package for RGB deep learning "
            "tree crown delineation. Methods in Ecology and Evolution 11: 1743–1751.",
        ),
    )
}


def num(value: Any, digits: int = 1) -> str:
    """A number for reading: thousands separated, fixed decimals; '—' when there is none."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "—"
    return f"{value:,.{digits}f}" if digits else f"{round(value):,}"


def ranged(spread: Any, unit: str = "", digits: int = 1, scale: float = 1.0) -> str:
    """'7.6 t (95% range 4.1–15.0 t)' from {'median', 'low', 'high'}."""
    if not isinstance(spread, Mapping) or not isinstance(spread.get("median"), int | float):
        return "—"
    tail = f" {unit}" if unit else ""
    mid = num(spread["median"] * scale, digits)
    low, high = spread.get("low"), spread.get("high")
    if not isinstance(low, int | float) or not isinstance(high, int | float):
        return f"{mid}{tail}"
    return (
        f"{mid}{tail} (95% range {num(low * scale, digits)}{DASH}{num(high * scale, digits)}{tail})"
    )


def _get(record: Record | None, *path: str) -> Any:
    found: Any = record
    for key in path:
        if not isinstance(found, Mapping):
            return None
        found = found.get(key)
    return found


def key_numbers(
    canopy: Record | None, surface: Record | None, inventory: Record | None
) -> list[tuple[str, str, str]]:
    """(what, value, note) for the summary table, in reading order."""
    rows: list[tuple[str, str, str]] = []
    area = _get(canopy, "area_m2") or _get(surface, "metrics", "area_m2")
    if isinstance(area, int | float):
        rows.append(("Area measured", f"{num(area / 10_000, 2)} ha", "after trimming the edges"))
    if canopy:
        rows += [
            (
                "Canopy cover",
                f"{num(canopy.get('canopy_cover_pct'))} %",
                f"cells at least {num(canopy.get('tree_height_threshold_m'))} m above ground",
            ),
            ("Canopy height, mean", f"{num(canopy.get('height_mean_m'))} m", "over canopy cells"),
            (
                "Canopy height, 95th percentile",
                f"{num(canopy.get('height_p95_m'))} m",
                "the top of the canopy, less sensitive to spikes than the maximum",
            ),
            ("Canopy height, maximum", f"{num(canopy.get('height_max_m'))} m", ""),
            (
                "Trees found",
                num(_get(canopy, "crowns", "trees") or canopy.get("tree_tops"), 0),
                f"{num(canopy.get('tree_tops_per_ha'))} per ha",
            ),
        ]
    cover = _get(surface, "metrics", "cover_pct")
    if isinstance(cover, Mapping) and cover:
        top = sorted(cover.items(), key=lambda kv: -kv[1] if isinstance(kv[1], int | float) else 0)
        text = ", ".join(f"{name} {num(value)} %" for name, value in top[:4])
        rows.append(("Land cover", text, "rules on height, colour and shadow"))
    biomass = _get(inventory, "biomass")
    if isinstance(biomass, Mapping):
        rows += [
            (
                "Above-ground biomass",
                ranged(biomass.get("agb_kg_jucker"), "t", 2, 0.001),
                "Jucker et al. 2017, Monte Carlo",
            ),
            ("Biomass per hectare", ranged(biomass.get("agb_t_per_ha_jucker"), "t/ha", 1), ""),
            (
                "Carbon",
                ranged(biomass.get("carbon_kg"), "t", 2, 0.001),
                f"carbon fraction {num(biomass.get('carbon_fraction'), 2)}",
            ),
            ("CO₂ equivalent", ranged(biomass.get("co2e_kg"), "t", 2, 0.001), "carbon × 44/12"),
            (
                "Second opinion (Chave et al. 2014)",
                ranged(biomass.get("agb_kg_chave"), "t", 2, 0.001),
                "a different equation: compare, do not average",
            ),
        ]
    grade = _get(inventory, "quality", "grade")
    if isinstance(grade, str):
        rows.append(("Quality grade of the height model", grade, "see Quality checks"))
    return rows


def _upper(text: str) -> str:
    """First letter upper case, the rest as written (keeps 'CIE Lab' and '3D')."""
    return text[:1].upper() + text[1:]


def _sentence(parts: list[str]) -> str:
    return " ".join(p for p in parts if p)


def _photos(prov: Record) -> list[str]:
    qa = _get(prov, "capture_qa", "stats") or {}
    rec = prov.get("reconstruction") or {}
    engine = prov.get("engine") or {}
    photos = rec.get("photos_total") or qa.get("photos_total")
    tool = f"{engine.get('engine', 'the map engine')} {engine.get('engine_version', '')}".strip()
    parts = [f"{num(photos, 0)} photos" if photos else "The photos"]
    if qa.get("gsd_cm_median"):
        parts.append(
            f"(median ground detail {num(qa['gsd_cm_median'], 2)} cm, "
            f"median height {num(qa.get('altitude_m_median'))} m)"
        )
    parts.append(f"were processed with {tool}, preset '{prov.get('preset', '?')}'.")
    if rec.get("photos_placed"):
        parts.append(
            f"{num(rec['photos_placed'], 0)} photos were placed; mean reprojection error "
            f"{num(rec.get('reprojection_px'), 2)} px."
        )
    if rec.get("gsd_cm_measured"):
        parts.append(f"Ground detail of the orthophoto: {num(rec['gsd_cm_measured'], 2)} cm.")
    if qa:
        parts.append("Photo overlap was checked from the photos' metadata before processing.")
    return [_sentence(parts)]


def _canopy(canopy: Record) -> list[str]:
    choice = canopy.get("ground_choice") or {}
    ground = str(canopy.get("ground_model") or choice.get("kind", "unknown"))
    ground = ground.removeprefix("ground: ")
    parts = [
        "The canopy height model is the surface model minus a ground model, on a "
        f"{num(canopy.get('cell_m'), 2)} m grid.",
        f"Ground: {ground}.",
        f"Ground was seen in {num(canopy.get('ground_seen_pct'))} % of the area.",
    ]
    if choice.get("aligned_on_cells"):
        parts.append(
            f"The outside ground model was shifted by {num(choice.get('shift_m'), 2)} m to "
            f"match the seen ground ({num(choice['aligned_on_cells'], 0)} cells)."
        )
    if canopy.get("edge_trimmed_m"):
        parts.append(
            f"{num(canopy['edge_trimmed_m'])} m was trimmed from the edges, where the "
            "reconstruction is weakest."
        )
    if _get(canopy, "crowns", "method"):
        parts.append(f"Tree crowns: {_get(canopy, 'crowns', 'method')}.")
    return [_sentence(parts)]


def _land(surface: Record) -> list[str]:
    parts = [_upper(f"{surface['method']}.") if surface.get("method") else ""]
    if surface.get("crown_detector"):
        parts.append(f"Crown detector: {surface['crown_detector']}.")
    return [_sentence(parts)]


def _heat(heat: Record) -> list[str]:
    return [
        _sentence(
            [
                f"Heat exposure: {heat.get('method')}, on {heat.get('day')} at "
                f"{num(heat.get('sun_positions'), 0)} sun positions.",
                "Mean rank of green cells "
                f"{num(heat.get('index_mean_green'), 2)}, of other cells "
                f"{num(heat.get('index_mean_not_green'), 2)}.",
                "An RGB camera does not measure heat: this ranks where daytime heating is likely "
                "and must be checked against a thermal camera before it is reported as heat.",
            ]
        )
    ]


def _trees(inventory: Record) -> list[str]:
    cal = inventory.get("height_calibration") or {}
    bio = inventory.get("biomass") or {}
    heights = [f"Tree heights: {cal['note']}." if cal.get("note") else ""]
    if cal.get("matched"):
        heights.append(
            f"Calibrated on {num(cal['matched'], 0)} field trees: height = "
            f"{num(cal.get('intercept_m'), 2)} m + {num(cal.get('slope'), 3)} × model height; "
            f"RMSE {num(cal.get('rmse_before_m'), 2)} m before, "
            f"{num(cal.get('rmse_loo_m'), 2)} m after (leave-one-out)."
        )
    found = [_sentence(heights)]
    if bio:
        found.append(
            _sentence(
                [
                    f"Biomass: {bio.get('method')}.",
                    f"Wood density {num(bio.get('wood_density'), 2)} g/cm³; "
                    f"{num(bio.get('draws'), 0)} Monte Carlo draws; ranges are the 2.5th and "
                    "97.5th percentiles.",
                    f"A single tree's estimate spans about {num(bio.get('one_tree_band'), 1)} "
                    "times either way, so read tree values as rough and stand totals as the "
                    "result.",
                ]
            )
        )
    return found


def methods(
    provenance: Record | None,
    canopy: Record | None,
    surface: Record | None,
    inventory: Record | None,
) -> list[tuple[str, list[str]]]:
    """(heading, paragraphs) for the methods section; only what was actually done."""
    found: list[tuple[str, list[str]]] = []
    if provenance:
        found.append(("Photos and reconstruction", _photos(provenance)))
    if canopy:
        found.append(("Canopy height model", _canopy(canopy)))
    if surface:
        found.append(("Land cover", _land(surface)))
        heat = surface.get("heat")
        if isinstance(heat, Mapping) and heat.get("made"):
            found.append(("Heat exposure (relative)", _heat(heat)))
    if inventory:
        found.append(("Trees, biomass and carbon", _trees(inventory)))
    return [(h, [p for p in ps if p]) for h, ps in found if any(ps)]


def findings(canopy: Record | None, surface: Record | None, inventory: Record | None) -> list[str]:
    """Every warning the engines wrote, each once, in order."""
    seen: list[str] = []
    for source in (
        _get(inventory, "quality", "findings"),
        [i.get("message") for i in (_get(canopy, "issues") or []) if isinstance(i, Mapping)],
        [i.get("message") for i in (_get(surface, "issues") or []) if isinstance(i, Mapping)],
        _get(inventory, "symptoms", "notes"),
    ):
        for text in source or []:
            if isinstance(text, str) and text not in seen:
                seen.append(text)
    return seen


def references(provenance: Record | None, inventory: Record | None) -> list[str]:
    """The references for what was used, in the order they are cited."""
    keys = ["odm"] if provenance else []
    if _get(inventory, "biomass"):
        keys += ["jucker", "chave", "ipcc"]
    if _get(inventory, "assumptions", "inputs", "deepforest"):
        keys.append("deepforest")
    return [REFERENCES[k].text for k in keys]
