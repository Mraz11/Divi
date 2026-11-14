# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Monoline icons: every icon name used on the screens, drawn with a Lucide outline.

The screens keep naming icons the Material way (``"folder"``, ``"check_circle"``), as Quasar does
for its own arrows and close buttons. A small function given to Quasar at start-up turns each
known name into a class whose shape is a 1.5-stroke Lucide outline (``assets/icons.css``, made by
``scripts/make_icons.py``); a name not listed here falls back to Quasar's own icon font.
The shapes are drawn as masks filled with the text colour, so an icon inverts with its button.
"""

from __future__ import annotations

import json

# Material name (ours and Quasar's) -> Lucide name
ICONS: dict[str, str] = {
    # used by the screens
    "add": "plus",
    "arrow_forward": "arrow-right",
    "arrow_upward": "arrow-up",
    "check": "check",
    "check_circle": "circle-check",
    "check_circle_outline": "circle-check",
    "crop_square": "square",
    "dark_mode": "moon",
    "delete": "trash-2",
    "delete_sweep": "trash",
    "description": "file-text",
    "download": "download",
    "edit": "pencil",
    "edit_location_alt": "map-pin-pen",
    "error": "circle-alert",
    "fact_check": "clipboard-check",
    "flight": "plane",
    "flight_takeoff": "plane-takeoff",
    "folder": "folder",
    "fullscreen": "maximize",
    "auto_fix_high": "wand-sparkles",
    "park": "trees",
    "fullscreen_exit": "minimize",
    "folder_open": "folder-open",
    "open_in_new": "external-link",
    "output": "file-output",
    "visibility": "eye",
    "save": "save",
    "image": "image",
    "help_outline": "circle-question-mark",
    "info": "info",
    "insert_drive_file": "file",
    "layers": "layers",
    "light_mode": "sun",
    "list": "list",
    "map": "map",
    "memory": "cpu",
    "my_location": "locate-fixed",
    "phone_android": "smartphone",
    "photo_library": "images",
    "play_arrow": "play",
    "polyline": "spline",
    "radio_button_checked": "circle-dot",
    "radio_button_unchecked": "circle",
    "refresh": "refresh-cw",
    "remove": "minus",
    "replay": "rotate-ccw",
    "report": "octagon-alert",
    "restart_alt": "rotate-ccw",
    "search": "search",
    "send": "send",
    "stop": "square",
    "table_rows": "rows-3",
    "terminal": "terminal",
    "terrain": "mountain",
    "timeline": "route",
    "tune": "sliders-horizontal",
    "undo": "undo-2",
    "warning": "triangle-alert",
    "wifi": "wifi",
    # Quasar's own (selects, expansions, chips, tables, notifications)
    "arrow_back": "arrow-left",
    "arrow_downward": "arrow-down",
    "arrow_drop_down": "chevron-down",
    "cancel": "circle-x",
    "chevron_left": "chevron-left",
    "chevron_right": "chevron-right",
    "clear": "x",
    "close": "x",
    "done": "check",
    "first_page": "chevrons-left",
    "keyboard_arrow_down": "chevron-down",
    "keyboard_arrow_left": "chevron-left",
    "keyboard_arrow_right": "chevron-right",
    "keyboard_arrow_up": "chevron-up",
    "last_page": "chevrons-right",
    "priority_high": "circle-alert",
}

ICON_CLASS = "dv-i"
# the map's own buttons (Leaflet.draw draws them from a picture that is dark on dark): each
# button's class -> its Lucide outline, drawn in the text colour like every other icon
LEAFLET_ICONS: dict[str, str] = {
    "leaflet-draw-draw-polyline": "spline",
    "leaflet-draw-draw-polygon": "pentagon",
    "leaflet-draw-draw-rectangle": "square",
    "leaflet-draw-draw-circle": "circle",
    "leaflet-draw-draw-marker": "map-pin",
    "leaflet-draw-draw-circlemarker": "circle-dot",
    "leaflet-draw-edit-edit": "pencil",
    "leaflet-draw-edit-remove": "trash-2",
    "leaflet-control-layers-toggle": "layers",
}


def css_class(lucide: str) -> str:
    return f"{ICON_CLASS} {ICON_CLASS}-{lucide}"


def icon_map_js() -> str:
    """Quasar's ``iconMapFn``, set before Quasar starts (NiceGUI's ``vue_config_script``)."""
    table = json.dumps({name: css_class(lucide) for name, lucide in sorted(ICONS.items())})
    return (
        f"\nconst DIVI_ICONS = {table};\n"
        "vue_config.iconMapFn = (name) =>\n"
        "  (name in DIVI_ICONS ? {cls: DIVI_ICONS[name]} : void 0);\n"
    )
