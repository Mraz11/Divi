# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `pipeline`, `status`, `export`, `report` and `cite` commands: the project as a whole."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from avispria.app.cli._base import app
from avispria.app.engines import Links, inspect
from avispria.app.export_rasters import ExportError
from avispria.app.export_workflow import ExportOptions, run_export
from avispria.app.export_workflow import describe as describe_export
from avispria.app.project import ProjectError, is_project, load_project
from avispria.app.report_workflow import ReportError, write_record
from avispria.core.citation import REQUEST, citation
from avispria.core.pipeline import ENGINES, diagram

_COLOUR = {
    "done": typer.colors.GREEN,
    "partial": typer.colors.YELLOW,
    "ready": typer.colors.CYAN,
    "waiting": typer.colors.BRIGHT_BLACK,
}


def _project(folder: Path) -> tuple[str, Links, dict[str, dict[str, str]]]:
    """A project folder (with a project record), or a maps folder on its own."""
    if is_project(folder):
        try:
            found = load_project(folder)
        except ProjectError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(2) from None
        links = Links(
            tuple(found.plan_files), tuple(found.sent_files), found.photo_folder, found.maps_folder
        )
        return found.name, links, found.engines
    if (folder / "results").is_dir():
        return folder.name, Links(maps_folder=str(folder)), {}
    typer.secho(
        f"{folder} is neither a Dīvi project folder nor a maps folder (with 'results' inside).",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(2)


@app.command()
def pipeline() -> None:
    """Show the engines of Dīvi, in the order a project goes."""
    typer.secho(diagram(), bold=True)
    for spec in ENGINES:
        needs = f" (needs: {', '.join(spec.needs)})" if spec.needs else ""
        optional = " [optional]" if spec.optional else ""
        typer.echo(f"{spec.number}. {spec.name}{optional}: {spec.task}{needs}")
        typer.echo(f"   makes: {spec.makes}")


@app.command()
def status(
    folder: Annotated[Path, typer.Argument(help="A project folder, or a maps folder.")],
) -> None:
    """Where a project stands: the state of each engine, read from what is on disk."""
    name, links, _ = _project(folder)
    typer.secho(f"Project: {name}", bold=True)
    for state in inspect(links):
        typer.secho(
            f"{state.spec.number}. {state.spec.name:<12} {state.label:<22} {state.detail}",
            fg=_COLOUR[state.status],
        )


@app.command()
def report(
    folder: Annotated[Path, typer.Argument(help="A project folder, or a maps folder.")],
) -> None:
    """Write the project report (results, maps, methods, provenance, citation) as one HTML file."""
    name, links, stamps = _project(folder)
    try:
        path = write_record(links, name, stamps)
    except ReportError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from None
    typer.echo(f"Saved: {path}")


@app.command()
def cite() -> None:
    """How to cite Dīvi."""
    typer.echo(REQUEST)
    typer.echo(citation())


@app.command("export")
def export_command(
    folder: Annotated[Path, typer.Argument(help="A maps folder (with 'results' inside).")],
    bands: Annotated[bool, typer.Option(help="Red, green and blue as separate files")] = True,
    colour: Annotated[bool, typer.Option(help="The full-colour orthophoto")] = True,
    surfaces: Annotated[bool, typer.Option(help="DSM, DTM, CHM and ground uncertainty")] = True,
    analysis: Annotated[bool, typer.Option(help="Land cover and colour index bands")] = True,
    vectors: Annotated[bool, typer.Option(help="The GeoPackage of editable layers")] = True,
) -> None:
    """Export maps and measurements for QGIS: one GeoTIFF per band, styled, and a GeoPackage."""
    options = ExportOptions(bands, colour, surfaces, analysis, vectors)
    try:
        outcome = run_export(folder, options)
    except ExportError as exc:
        typer.secho(f"Nothing was exported: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from None
    typer.echo(f"Exported to {outcome.folder}")
    for line in describe_export(outcome):
        typer.echo(f"  {line}")
