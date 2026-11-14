# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared Typer app, helpers and small commands."""

from __future__ import annotations

import sys
from fractions import Fraction

import typer

from avispria.adapters.profiles import load_profiles
from avispria.core.safety import Issue
from avispria.core.version import __version__


def tolerate_any_console() -> None:
    """Print "ī" (and anything else) as "?" instead of crashing on a non-UTF-8 console."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


tolerate_any_console()

app = typer.Typer(
    name="avispria",
    help=(
        "Dīvi (command: avispria): offline-first planning, QA and analysis for consumer RGB "
        "drone surveys of forests, farms and towns. Fly. Analyze. Decide."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def print_issues(issues: list[Issue]) -> None:
    for i in issues:
        colour = typer.colors.RED if i.level == "error" else typer.colors.YELLOW
        typer.secho(f"  {i.level.upper():7} {i.code}  {i.message}", fg=colour)


def parse_latlon(text: str) -> tuple[float, float]:
    try:
        lat_s, lon_s = text.split(",")
        return float(lat_s), float(lon_s)
    except ValueError as exc:
        raise typer.BadParameter("use LAT,LON, e.g. 23.8103,90.4125") from exc


def parse_shutter(text: str) -> float:
    try:
        value = float(Fraction(text))
    except (ValueError, ZeroDivisionError) as exc:
        raise typer.BadParameter("use a fraction like 1/1000 or seconds like 0.001") from exc
    if value <= 0:
        raise typer.BadParameter("shutter must be positive")
    return value


@app.command()
def version() -> None:
    """Print the Dīvi version."""
    typer.echo(f"avispria {__version__}")


@app.command()
def drones() -> None:
    """List known aircraft profiles and camera modes."""
    for p in load_profiles().values():
        state = "verified" if p.verified else "UNVERIFIED"
        typer.echo(f"{p.key:12} {p.name:16} modes: {', '.join(p.modes)}  [{state}]")
