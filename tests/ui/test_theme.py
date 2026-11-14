# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import re
from dataclasses import fields

import pytest

from avispria.app.ui import theme
from avispria.app.ui.theme import DARK, LIGHT, contrast_ratio, mix, tokens_css

# (foreground, background, minimum contrast, what it is)
TEXT = 7.0  # body text: comfortably above the 4.5 minimum, for sunlight and tired eyes
SMALL = 4.5  # WCAG AA for small text
GRAPHIC = 3.0  # WCAG for large text, icons, lines and the edges of controls

PAIRS = [
    ("text", "bg", TEXT),
    ("text", "surface", TEXT),
    ("text", "surface_2", TEXT),
    ("muted", "bg", SMALL),
    ("muted", "surface", SMALL),
    ("muted", "surface_2", SMALL),
    ("primary_text", "bg", SMALL),
    ("primary_text", "surface", SMALL),
    ("primary_text", "surface_2", SMALL),
    ("primary_text", "good_bg", SMALL),
    ("on_primary", "primary", SMALL),
    ("on_secondary", "secondary", SMALL),
    ("on_highlight", "highlight", SMALL),
    ("secondary_text", "bg", SMALL),
    ("secondary_text", "surface", SMALL),
    ("secondary_text", "surface_2", SMALL),
    ("on_danger", "danger", SMALL),
    ("danger_text", "bg", SMALL),
    ("danger_text", "surface", SMALL),
    ("danger_text", "problem_bg", SMALL),
    ("highlight_text", "bg", SMALL),
    ("highlight_text", "surface", SMALL),
    ("highlight_text", "caution_bg", SMALL),
    ("text", "good_bg", TEXT),
    ("text", "caution_bg", TEXT),
    ("text", "problem_bg", TEXT),
    ("border_strong", "surface", GRAPHIC),
    ("border_strong", "bg", GRAPHIC),
    ("outline", "surface", GRAPHIC),
    ("points", "surface", GRAPHIC),
    ("marker", "surface", GRAPHIC),
]


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=lambda p: p.name)
@pytest.mark.parametrize(("fg", "bg", "minimum"), PAIRS, ids=lambda v: str(v))
def test_every_pairing_is_readable(
    palette: theme.Palette, fg: str, bg: str, minimum: float
) -> None:
    ratio = contrast_ratio(getattr(palette, fg), getattr(palette, bg))
    assert ratio >= minimum, f"{palette.name}: {fg} on {bg} is {ratio:.2f}:1, needs {minimum}:1"


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=lambda p: p.name)
def test_chart_lines_and_dots_show_up_on_the_card_colour(palette: theme.Palette) -> None:
    for colour in palette.missions:
        assert contrast_ratio(colour, palette.surface) >= GRAPHIC, f"{palette.name}: {colour}"


def test_the_logo_colours_are_used_exactly_as_given_where_they_are_fills() -> None:
    logo = ("#669762", "#DBB241", "#7A96AA")  # vegetation, agriculture, urban (branding/logo.png)
    for p in (LIGHT, DARK):
        assert (p.primary, p.highlight, p.secondary) == logo, p.name
    assert LIGHT.outline == "#47545E"  # the drone's slate
    assert (DARK.bg, DARK.surface) == ("#0E1714", "#15211D")  # the telemetry console
    assert (DARK.outline, DARK.points) == ("#8EC5FF", "#7CF29A")  # data overlays in dark mode


def test_errors_never_share_a_colour_with_the_logo() -> None:
    for p in (LIGHT, DARK):
        assert p.danger not in (p.primary, p.secondary, p.highlight)


def test_both_modes_define_every_colour_in_hex() -> None:
    for f in fields(LIGHT):
        if f.name == "name":
            continue
        for p in (LIGHT, DARK):
            value = getattr(p, f.name)
            values = value if isinstance(value, tuple) else (value,)
            assert all(re.fullmatch(r"#[0-9A-F]{6}", v) for v in values), (p.name, f.name, value)
    assert (
        len(LIGHT.ramp) == len(DARK.ramp) == 3
        and len(LIGHT.missions) >= 6
        and len(DARK.missions) >= 6
    )


def test_the_contrast_checker_agrees_with_known_values() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)
    assert contrast_ratio("#669762", "#FFFFFF") < 4.5  # why white text is not used on the green
    assert mix("#000000", "#FFFFFF", 0.5) == "#808080"
    assert mix("#FF0000", "#FFFFFF", 0.0) == "#FFFFFF"


def test_css_gives_each_mode_its_variables() -> None:
    css = tokens_css(quasar=True)
    assert css.startswith(":root {") and "--bg: #EDF1EE;" in css and "--surface: #FFFFFF;" in css
    assert 'html[data-theme="dark"]' in css or ':root[data-theme="dark"]' in css
    assert "body.body--dark" in css and "--bg: #0E1714;" in css and "--primary: #669762;" in css
    assert "--q-negative: #C4513C !important;" in css and "--q-negative: #E07A63 !important;" in css
    # NiceGUI sets a blue primary as an inline style on <body>: only !important on body beats it
    assert "body {\n  --q-primary: #669762 !important;" in css
    assert "prefers-color-scheme: dark" in css  # the no-JavaScript fallback
    assert "--q-" not in tokens_css()  # the phone page does not need Quasar's names


def test_the_boot_script_sets_the_theme_before_anything_is_drawn() -> None:
    js = theme.THEME_BOOT_JS
    assert theme.STORAGE_KEY in js and "data-theme" in js and "prefers-color-scheme: dark" in js
    assert "try" in js  # a phone that refuses storage must not break the page
