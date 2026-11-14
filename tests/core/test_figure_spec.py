# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from avispria.core.figure_spec import (
    FigureError,
    FigureSpec,
    auto_height_mm,
    length_label,
    nice_length,
    pixels,
)


def test_a_good_description_passes_and_bad_ones_say_what_to_change() -> None:
    assert FigureSpec("chm").checked().dpi == 300
    for spec, message in (
        (FigureSpec(""), "Choose a map layer"),
        (FigureSpec("chm", width_mm=10), "width must be 20 to 600 mm"),
        (FigureSpec("chm", height_mm=700), "height must be"),
        (FigureSpec("chm", dpi=50), "resolution must be"),
        (FigureSpec("chm", fmt="jpg"), "Save as one of"),
        (FigureSpec("chm", ramp="rainbow"), "Colours: one of"),
        (FigureSpec("chm", low=5, high=5), "above the bottom"),
        (FigureSpec("chm", font_pt=40), "Text size"),
        (FigureSpec("chm", width_mm=600, height_mm=600, dpi=1200), "too many pixels"),
    ):
        with pytest.raises(FigureError, match=message):
            spec.checked()


def test_sizes_and_scale_bars() -> None:
    assert pixels(85, 300) == 1004 and pixels(25.4, 600) == 600
    assert nice_length(100) == 20 and nice_length(1000) == 200 and nice_length(37) == 5
    assert nice_length(8) == 2 and nice_length(0.5, 1.0) == 0.5
    with pytest.raises(FigureError, match="no extent"):
        nice_length(0)
    assert length_label(500) == "500 m" and length_label(2000) == "2 km"
    square = auto_height_mm(170, 1.0)
    assert 120 < square < 170  # the colour bar and labels take width
    assert auto_height_mm(170, 1.0, legend="none", grid=False) > square
    assert auto_height_mm(170, 1.0, title=True, caption_lines=2) > square
    assert auto_height_mm(170, 1.0, legend="classes", legend_chars=30) < square
    assert auto_height_mm(600, 10) == 600 and auto_height_mm(20, 0.01, grid=False) == 20
