# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""`avispria canopy`: canopy height, cover and tree tops from a results folder."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from avispria.app.canopy_workflow import (
    DEFAULT_CELL_M,
    DEFAULT_EDGE_M,
    DEFAULT_WINDOW_M,
    CanopyError,
    crowns_line,
    describe,
    run_canopy,
)
from avispria.app.cli._base import app, print_issues


@app.command()
def canopy(
    results: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="Results folder of `process`")
    ],
    cell: Annotated[float, typer.Option(help="Grid cell size (m)")] = DEFAULT_CELL_M,
    window: Annotated[
        float, typer.Option(help="Widest stand of trees with no open ground in it (m)")
    ] = DEFAULT_WINDOW_M,
    edge: Annotated[float, typer.Option(help="Rim of the map left out (m)")] = DEFAULT_EDGE_M,
) -> None:
    """Canopy height model (DSM minus ground), cover, gaps and tree tops."""
    try:
        outcome = run_canopy(results, cell_m=cell, window_m=window, edge_m=edge)
    except CanopyError as exc:
        typer.secho(f"Canopy model not made: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    for label, value in describe(outcome.stats):
        typer.echo(f"  {label:<48} {value}")
    if outcome.crowns is not None:
        typer.echo(f"  {crowns_line(outcome.crowns)}")
        print_issues(outcome.crowns.issues)
    print_issues(outcome.stats.issues)
    typer.echo(f"  height model  {outcome.chm_path}")
    typer.echo(f"  quick look    {outcome.preview_path}")
    typer.echo(f"  numbers       {outcome.summary_path}")
    if outcome.crowns_path is not None:
        typer.echo(f"  crowns        {outcome.crowns_path} (and crowns.csv)")
