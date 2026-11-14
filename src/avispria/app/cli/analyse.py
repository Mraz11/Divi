# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""`avispria analyse`: land cover, trees, buildings, roads and green numbers from results."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from avispria.app.canopy_workflow import CanopyError
from avispria.app.cli._base import app, print_issues
from avispria.app.clip_workflow import ClipError, clip_results, restore_uncut
from avispria.app.inventory_workflow import TreeInputs, describe_inventory, write_rank_change
from avispria.app.surface_workflow import describe_analysis, run_analysis
from avispria.core.analyses import KEYS, SwitchError, checked
from avispria.core.biomass import BiomassInputs
from avispria.core.ground_sources import OUTSIDE_KINDS
from avispria.core.profiles import PROFILES


@app.command()
def analyse(
    results: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="Results folder of `process`")
    ],
    profile: Annotated[
        str, typer.Option(help=f"What was mapped: {', '.join(PROFILES)}")
    ] = "forest",
    cell: Annotated[float, typer.Option(help="Grid cell size (m)")] = 0.5,
    ground: Annotated[
        Path | None, typer.Option(exists=True, help="An outside ground model (GeoTIFF)")
    ] = None,
    ground_kind: Annotated[
        str, typer.Option(help=f"What --ground is: {', '.join(OUTSIDE_KINDS)}")
    ] = "lidar",
    reference: Annotated[
        Path | None,
        typer.Option(exists=True, help="An independent ground model for the doming check"),
    ] = None,
    field_heights: Annotated[
        Path | None,
        typer.Option(exists=True, help="CSV of trees measured on the ground: lat, lon, height_m"),
    ] = None,
    wood_density: Annotated[float, typer.Option(help="Mean wood density (g/cm3)")] = 0.6,
    wood_density_sd: Annotated[float, typer.Option(help="Its uncertainty (g/cm3)")] = 0.1,
    carbon_fraction: Annotated[float, typer.Option(help="Carbon share of dry biomass")] = 0.47,
    conifer: Annotated[bool, typer.Option(help="Conifers (gymnosperms)")] = False,
    draws: Annotated[int, typer.Option(help="Monte Carlo runs")] = 1000,
    deepforest: Annotated[
        bool, typer.Option(help="Correct crowns with DeepForest (uv sync --extra trees)")
    ] = False,
    off: Annotated[
        list[str] | None,
        typer.Option(help=f"Switch an analysis off (repeat for more): {', '.join(KEYS)}"),
    ] = None,
) -> None:
    """Land cover, trees, buildings, roads, green numbers, and the tree inventory: checked
    heights, biomass and carbon with ranges, visible symptoms, colour indices."""
    if profile not in PROFILES:
        typer.secho(f"Unknown profile {profile!r}: choose {', '.join(PROFILES)}", fg="red")
        raise typer.Exit(2)
    try:
        switched = checked(off or ())
    except SwitchError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(2) from None
    trees = TreeInputs(
        off=switched,
        ground_file=ground,
        ground_kind=ground_kind,
        reference_file=reference,
        field_heights=field_heights,
        deepforest=deepforest,
        biomass=BiomassInputs(
            wood_density=wood_density,
            wood_density_sd=wood_density_sd,
            carbon_fraction=carbon_fraction,
            conifer=conifer,
            draws=draws,
        ),
    )
    try:
        outcome = run_analysis(results, profile, cell_m=cell, trees=trees)
    except (CanopyError, ValueError) as exc:
        typer.secho(f"Analysis not made: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    for label, value in describe_analysis(outcome.result.metrics):
        typer.echo(f"  {label:<48} {value}")
    if outcome.inventory is not None:
        for label, value in describe_inventory(outcome.inventory):
            typer.echo(f"  {label:<48} {value}")
    print_issues(outcome.result.issues)
    typer.echo(f"  land cover    {outcome.landcover_path}")
    typer.echo(f"  numbers       {outcome.summary_path}")
    if outcome.inventory is not None:
        typer.echo(f"  trees         {outcome.inventory.trees_path}")


@app.command("compare-flights")
def compare_flights(
    before: Annotated[Path, typer.Argument(exists=True, help="An index GeoTIFF, earlier flight")],
    after: Annotated[Path, typer.Argument(exists=True, help="The same index, later flight")],
    out: Annotated[Path, typer.Option(help="The change GeoTIFF to write")] = Path(
        "rank_change.tif"
    ),
) -> None:
    """Change of a colour index between two flights, by rank within each flight (relative)."""
    write_rank_change(before, after, out)
    typer.echo(f"Written: {out} (percentile points; - = less than the rest of its flight)")


@app.command()
def clip(
    results: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="Results folder of `process`")
    ],
    area: Annotated[
        Path | None,
        typer.Argument(exists=True, help="The area: KML, KMZ, SHP (with .shx/.prj), ZIP, GeoJSON"),
    ] = None,
    buffer: Annotated[float, typer.Option(help="Widen the area by this many metres")] = 0.0,
    undo: Annotated[bool, typer.Option(help="Put the uncut maps back")] = False,
) -> None:
    """Cut the stitched maps (orthophoto, surface and ground models) to an area."""
    if undo:
        back = restore_uncut(results)
        typer.echo(f"Uncut maps put back: {len(back)}")
        return
    if area is None:
        typer.secho("Give the area file to cut by (or --undo).", fg=typer.colors.RED)
        raise typer.Exit(2)
    try:
        outcome = clip_results(results, area, buffer)
    except ClipError as exc:
        typer.secho(f"Not cut: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    for path in outcome.cut:
        typer.echo(f"  cut  {path}")
    if outcome.area_m2 is not None:
        typer.echo(f"  area {outcome.area_m2 / 10_000:.2f} ha; originals kept as *.full.tif")
