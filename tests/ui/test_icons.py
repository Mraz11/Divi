# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every icon the screens name is drawn as a Lucide outline, and the shapes file matches the map."""

import re
from pathlib import Path

from nicegui import app

from avispria.app.ui.icons import ICONS, css_class, icon_map_js
from avispria.app.ui.layout import ASSETS, install_look

UI = Path(__file__).resolve().parents[2] / "src" / "avispria" / "app" / "ui"


def named_icons() -> set[str]:
    names: set[str] = set()
    for path in UI.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        names |= set(re.findall(r'icon="([a-z_]+)"', text))
        names |= set(re.findall(r'ui\.icon\(\s*"([a-z_]+)"', text))
        names |= set(re.findall(r'"(check_circle|warning|error|radio_button_[a-z]+)"', text))
    return names


def test_every_icon_on_the_screens_has_an_outline() -> None:
    from avispria.app.ui.journey import STEPS
    from avispria.app.ui.pages.plan_map_text import KIND_ICONS

    used = named_icons() | {s.icon for s in STEPS} | set(KIND_ICONS.values())
    missing = sorted(used - set(ICONS))
    assert missing == [], (
        f"add these to ICONS in icons.py, then run scripts/make_icons.py: {missing}"
    )


def test_the_shapes_file_has_every_outline_and_nothing_else() -> None:
    css = (ASSETS / "icons.css").read_text(encoding="utf-8")
    drawn = set(re.findall(r"^\.dv-i-([a-z0-9-]+) \{", css, flags=re.M))
    assert drawn == set(ICONS.values())
    assert "ISC License" in css and "stroke-width%3D%221.5%22" in css


def test_quasar_is_told_before_it_starts_and_only_once() -> None:
    install_look()
    install_look()
    assert app.config.vue_config_script.count("DIVI_ICONS = ") == 1
    assert app.config.vue_config_script.index("iconMapFn") < app.config.vue_config_script.index(
        "app.use(Quasar"
    )
    assert '"folder": "' + css_class("folder") + '"' in icon_map_js()


def test_the_font_ships_with_the_program_and_its_licence() -> None:
    fonts = ASSETS / "fonts"
    for name in ("jetbrains-mono-latin.woff2", "jetbrains-mono-latin-ext.woff2"):
        assert (fonts / name).read_bytes()[:4] == b"wOF2"
    assert "SIL Open Font License" in (fonts / "OFL.txt").read_text(encoding="utf-8")
