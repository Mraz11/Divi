# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `process` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from avispria.adapters.engine import EngineError
from avispria.app.cli._base import app
from avispria.app.process_work import WorkError
from avispria.app.process_workflow import (
    ProcessBlockedError,
    ProcessRequest,
    request_from_work,
    run_process,
)
from avispria.core.feasibility import gb
from avispria.core.processing import DEFAULT_RESIZE_MP, PRESETS
from avispria.core.profiles import PROFILES


class _ConsoleReporter:
    def __init__(self) -> None:
        self._last: tuple[int, str] | None = None

    def step(self, title: str) -> None:
        typer.secho(f"\n{title}", bold=True)

    def info(self, text: str) -> None:
        typer.echo(f"  {text}")

    def warn(self, text: str) -> None:
        typer.secho(f"  ! {text}", fg=typer.colors.YELLOW)

    def upload(self, percent: float) -> None:
        self._show(percent, "uploaded")

    def progress(self, percent: float, status: str) -> None:
        self._show(percent, status.lower())

    def _show(self, percent: float, label: str) -> None:
        bucket = (int(percent) // 10 * 10, label)
        if bucket != self._last:  # print every 10% or on status change
            self._last = bucket
            typer.echo(f"  {bucket[0]:3d}% {label}")


@app.command()
def process(
    folder: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Photo folder")],
    out: Annotated[Path, typer.Option(help="Folder for results and the provenance record")],
    preset: Annotated[str, typer.Option(help=f"One of: {', '.join(PRESETS)}")] = "standard",
    recursive: Annotated[bool, typer.Option("--recursive", "-r")] = False,
    full_resolution: Annotated[
        bool, typer.Option(help=f"Send photos at full size (default: {DEFAULT_RESIZE_MP:g} MP)")
    ] = False,
    force: Annotated[
        bool, typer.Option(help="Start even if this computer seems too small")
    ] = False,
    url: Annotated[str | None, typer.Option(help="Engine address (default: WebODM's)")] = None,
    token: Annotated[str | None, typer.Option(help="Engine token (default: read from it)")] = None,
    name: Annotated[str | None, typer.Option(help="Task name (default: folder name)")] = None,
    profile: Annotated[
        str, typer.Option(help=f"What was mapped: {', '.join(PROFILES)}")
    ] = "forest",
    keep_repeats: Annotated[
        bool, typer.Option(help="Also send photos taken while hovering or in a repeated pass")
    ] = False,
    clip: Annotated[
        Path | None,
        typer.Option(
            exists=True, help="Cut the stitched maps to this area (KML, KMZ, SHP, ZIP, GeoJSON)"
        ),
    ] = None,
    clip_buffer: Annotated[float, typer.Option(help="Widen the cut by this many metres")] = 0.0,
) -> None:
    """Check, upload and process a photo folder; download results with a provenance record."""
    if preset not in PRESETS:
        raise typer.BadParameter(f"unknown preset {preset!r}; choose {', '.join(PRESETS)}")
    if profile not in PROFILES:
        raise typer.BadParameter(f"unknown profile {profile!r}; choose {', '.join(PROFILES)}")
    request = ProcessRequest(
        folder=folder,
        out_dir=out,
        preset=preset,  # type: ignore[arg-type]
        recursive=recursive,
        resize_mp=None if full_resolution else DEFAULT_RESIZE_MP,
        force=force,
        url=url,
        token=token,
        name=name,
        profile=profile,
        keep_repeats=keep_repeats,
        clip_file=clip,
        clip_buffer_m=clip_buffer,
    )
    _run(request)


@app.command()
def resume(
    results: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="The results folder of the job")
    ],
    token: Annotated[str | None, typer.Option(help="Engine token (default: read from it)")] = None,
    force: Annotated[
        bool, typer.Option(help="Start even if this computer seems too small")
    ] = False,
) -> None:
    """Continue a processing job that stopped half way, from its results folder."""
    try:
        request = request_from_work(results, token=token, force=force)
    except WorkError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    _run(request)


def _run(request: ProcessRequest) -> None:
    try:
        outcome = run_process(request, _ConsoleReporter())
    except ProcessBlockedError as exc:
        typer.secho(f"\nNot started: {exc}", fg=typer.colors.RED)
        if exc.assessment is not None:
            typer.echo("What you can do:")
            for n, o in enumerate(exc.assessment.options, start=1):
                need = "" if o.ram_gb is None else f" [about {gb(o.ram_gb)} GB]"
                typer.echo(f"  {n}. {o.description}{need}")
            typer.echo("Or add --force to try anyway.")
        raise typer.Exit(1) from exc
    except EngineError as exc:
        typer.secho(f"\nEngine problem: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    if not outcome.completed:
        typer.secho(
            f"\nProcessing {outcome.task.status.lower()}: {outcome.task.error}", fg=typer.colors.RED
        )
        for line in outcome.task.log_tail[-15:]:
            typer.echo(f"  | {line}")
        typer.echo(f"Details saved in {outcome.provenance_path}")
        typer.echo(f"To continue later:  divi resume {request.out_dir}")
        raise typer.Exit(1)
    typer.secho(
        f"\nDone in {outcome.task.processing_s / 60:.1f} min of processing.",
        fg=typer.colors.GREEN,
        bold=True,
    )
    typer.echo(f"  results       {outcome.results_dir}")
    typer.echo(
        f"  all outputs   {outcome.zip_path}  (WebODM: Import -> this file to view it there)"
    )
    typer.echo(f"  provenance    {outcome.provenance_path}")
