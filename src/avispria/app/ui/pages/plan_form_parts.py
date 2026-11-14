# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small building blocks shared by the Plan a flight form's cards."""

from __future__ import annotations

from collections.abc import Iterable

from nicegui import ui

# JetBrains Mono's letters are all 0.6 em wide, so a box's width can be worked out from its text:
# the small capitals of a label (11.5 px, spaced) and the value (16 px), plus the padding.
LABEL_PX = 8.1
VALUE_PX = 9.7
PAD_PX = 30
ARROW_PX = 34


def fit_px(label: str, values: Iterable[str] = (), arrow: bool = False) -> int:
    """The width in pixels a field needs so its label and longest value are not cut off."""
    longest = max((len(v) for v in values), default=0)
    need = max(len(label) * LABEL_PX, longest * VALUE_PX) + PAD_PX + (ARROW_PX if arrow else 0)
    return int(need + 0.5)


def fit(field: ui.element, label: str, values: Iterable[str] = (), arrow: bool = False) -> None:
    """Make ``field`` at least as wide as its text needs (on a phone fields are full width)."""
    field.style(f"min-width: {fit_px(label, values, arrow)}px")


def select_fit(field: ui.select, label: str) -> ui.select:
    """A select as wide as its label and its longest choice."""
    options = field.options
    texts = options.values() if isinstance(options, dict) else (str(o) for o in options)
    fit(field, label, [str(t) for t in texts], arrow=True)
    return field


def card(
    title: str, *, radio: ui.radio | None = None, kinds: tuple[str, ...] | None = None
) -> ui.column:
    """A titled card. With ``radio`` and ``kinds`` it is only visible for those scan types."""
    with ui.card().classes("w-full") as outer:
        ui.label(title).classes("text-lg font-bold")
        inner = ui.column().classes("w-full gap-3")
    if radio is not None and kinds is not None:
        outer.bind_visibility_from(radio, "value", backward=lambda v: v in kinds)
    return inner


def number(
    label: str, value: float, marker: str, width: str = "w-40", **limits: float
) -> ui.number:
    field = ui.number(label, value=value, **limits).props("outlined dense").mark(marker)
    fit(field, label, [f"{value:g}"])
    return field.classes(width)


def text(label: str, marker: str, value: str = "", width: str = "w-full", **kw: str) -> ui.input:
    field = ui.input(label, value=value, **kw).props("outlined dense").classes(width)
    fit(field, label, [value, kw.get("placeholder", "")])
    return field.mark(marker)


def show_when(mode: ui.radio, wanted: str, gap: str = "gap-3") -> ui.column:
    """A column that is only visible while the radio group has the value ``wanted``."""
    column = ui.column().classes(f"w-full {gap}")
    column.bind_visibility_from(mode, "value", backward=lambda v: v == wanted)
    return column


def show_when_in(radio: ui.radio, wanted: tuple[str, ...], gap: str = "gap-3") -> ui.column:
    """A column that is only visible while the radio group has one of the values in ``wanted``."""
    column = ui.column().classes(f"w-full {gap}")
    column.bind_visibility_from(radio, "value", backward=lambda v: v in wanted)
    return column
