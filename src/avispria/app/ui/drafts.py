# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a screen had filled in, kept while the program runs, so going to another step and back
loses nothing.

Every page is rebuilt from scratch when it is opened, so without this a mistake found on a later
step could only be fixed by filling the earlier one in again. Drafts live in memory only: they
may hold coordinates, which never go to disk (see ``state.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from nicegui.elements.mixins.value_element import ValueElement

DRAFTS: dict[str, dict[str, Any]] = {}  # page -> field name -> value


def _fields(owner: object, prefix: str = "") -> Iterator[tuple[str, ValueElement]]:
    """The value widgets held by ``owner``'s attributes, and by their ``input`` (PathField)."""
    for name, value in vars(owner).items():
        if name.startswith("_"):
            continue
        if isinstance(value, ValueElement):
            yield prefix + name, value
        elif isinstance(getattr(value, "input", None), ValueElement):
            yield f"{prefix}{name}.input", value.input


def keep(page: str, owner: object) -> None:
    """Put back what ``owner``'s widgets held the last time ``page`` was open, and keep it fresh.

    Call once the widgets exist. Values are put back in the order the widgets were made, so a
    choice that reveals other fields comes before them.
    """
    saved = DRAFTS.setdefault(page, {})
    for name, widget in _fields(owner):
        if name in saved and saved[name] != widget.value:
            try:
                widget.value = saved[name]
            except (ValueError, TypeError):  # an option that no longer exists
                saved.pop(name, None)

        def store(event: Any, key: str = name) -> None:
            saved[key] = event.value

        widget.on_value_change(store)


def remember(page: str, key: str, value: Any) -> None:
    """Keep something that is not a widget (the shapes on a map, the last result)."""
    DRAFTS.setdefault(page, {})[key] = value


def recall(page: str, key: str, default: Any = None) -> Any:
    return DRAFTS.get(page, {}).get(key, default)


def forget(page: str | None = None) -> None:
    """Start a page (or every page) afresh."""
    if page is None:
        DRAFTS.clear()
    else:
        DRAFTS.pop(page, None)
