# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map images: every kind of layer draws, saves in every format, and refuses what it cannot."""

import io
from pathlib import Path

import pytest
from PIL import Image

from avispria.app.figure import draw, layers, preview, save
from avispria.app.inventory_workflow import TreeInputs
from avispria.app.surface_workflow import run_analysis
from avispria.app.ui.after_job import AfterError
from avispria.app.ui.figure_job import (
    CUSTOM,
    FigureForm,
    file_name,
    layer_choices,
    preview_job,
    save_job,
    size_text,
)
from avispria.core.figure_spec import FigureError, FigureSpec
from forestscene import scene


@pytest.fixture(scope="module")
def results(tmp_path_factory: pytest.TempPathFactory) -> Path:
    found, _ = scene(tmp_path_factory.mktemp("fig"))
    run_analysis(found, "forest", trees=TreeInputs())
    return found


def test_every_layer_of_the_project_is_offered(results: Path) -> None:
    found = layers(results)
    assert {"orthophoto", "chm", "dsm", "landcover", "index:gcc"} <= set(found)
    assert found["chm"].unit == "m" and found["landcover"].kind == "classes"


@pytest.mark.parametrize("layer", ["orthophoto", "chm", "landcover", "index:gcc"])
def test_each_kind_of_layer_draws_with_its_furniture(results: Path, layer: str) -> None:
    fig = draw(
        FigureSpec(
            layer, width_mm=85, dpi=100, title="T", caption="C" * 300, crowns=layer == "chm"
        ),
        results,
    )
    texts = [t.get_text() for t in fig.findobj(lambda o: hasattr(o, "get_text"))]
    assert "T" in texts and "N" in texts and any(t.endswith(" m") for t in texts)
    assert fig.get_figwidth() == pytest.approx(85 / 25.4)


def test_furniture_can_be_left_out_and_colours_changed(results: Path) -> None:
    spec = FigureSpec(
        "chm",
        width_mm=85,
        height_mm=60,
        dpi=100,
        legend=False,
        north_arrow=False,
        scale_bar=False,
        grid=False,
        ramp="viridis",
        low=0,
        high=10,
    )
    fig = draw(spec, results)
    texts = [t.get_text() for t in fig.findobj(lambda o: hasattr(o, "get_text"))]
    assert "N" not in texts and fig.get_figheight() == pytest.approx(60 / 25.4)
    assert len(fig.axes) == 1  # no colour bar
    with pytest.raises(FigureError, match="not in this project"):
        draw(FigureSpec("nothing"), results)


@pytest.mark.parametrize("fmt", ["png", "tif", "pdf", "svg"])
def test_images_are_saved_at_the_chosen_size(results: Path, tmp_path: Path, fmt: str) -> None:
    path = save(
        FigureSpec("chm", width_mm=85, height_mm=60, dpi=200, fmt=fmt), results, tmp_path / "map"
    )
    assert path.suffix == f".{fmt}" and path.stat().st_size > 1000
    if fmt in {"png", "tif"}:
        with Image.open(path) as image:
            assert abs(image.width - 669) <= 1 and abs(image.height - 472) <= 1
    if fmt == "svg":
        assert "<svg" in path.read_text("utf-8")


def test_the_preview_is_the_same_layout_at_screen_resolution(results: Path) -> None:
    png = preview(FigureSpec("chm", width_mm=170, height_mm=100, dpi=600), results)
    with Image.open(io.BytesIO(png)) as image:
        assert abs(image.width - 602) <= 1  # 170 mm at 90 dpi, not 600


def test_crowns_need_measured_maps(tmp_path: Path) -> None:
    bare, _ = scene(tmp_path)
    with pytest.raises(FigureError, match="no tree crowns yet"):
        draw(FigureSpec("orthophoto", dpi=72, crowns=True), bare)


def _form(folder: Path, **kw: object) -> FigureForm:
    base: dict[str, object] = {
        "folder": str(folder),
        "layer": "chm",
        "width_choice": "Journal, 1 column (85 mm)",
        "custom_width_mm": None,
        "auto_height": True,
        "height_mm": None,
        "dpi": 150,
        "fmt": "png",
    }
    return FigureForm(**(base | kw))  # type: ignore[arg-type]


def test_the_form_becomes_a_figure_and_is_saved_without_overwriting(results: Path) -> None:
    maps = results.parent
    assert "chm" in layer_choices(str(maps)) and layer_choices("") == {}
    assert size_text(_form(maps)) == "85 mm wide, height fits the map; 150 dpi = 502 pixels wide"
    assert size_text(_form(maps, width_choice=CUSTOM)) == ""
    with pytest.raises(FigureError, match="width in millimetres"):
        _form(maps, width_choice=CUSTOM).spec()
    with pytest.raises(FigureError, match="Give the height"):
        _form(maps, auto_height=False).spec()
    assert _form(maps, width_choice=CUSTOM, custom_width_mm=100).spec().width_mm == 100
    assert preview_job(_form(maps)).startswith("data:image/png;base64,")
    first = save_job(_form(maps, title="Sal block A / CHM"))
    second = save_job(_form(maps, title="Sal block A / CHM"))
    assert first.name == "Sal_block_A_CHM.png" and second.name == "Sal_block_A_CHM-2.png"
    assert first.parent == maps / "export" / "figures"
    assert file_name(_form(maps, layer="index:gcc")) == "index_gcc"
    for call in (preview_job, save_job):
        with pytest.raises(AfterError, match="Choose a map layer"):
            call(_form(maps, layer=""))
