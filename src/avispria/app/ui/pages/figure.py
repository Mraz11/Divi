# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Step 7, second screen: map images for publication, previewed before they are saved."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from avispria.app.ui.figure_job import (
    CUSTOM,
    FIGURES_DIR,
    FigureForm,
    layer_choices,
    preview_job,
    save_job,
    size_text,
)
from avispria.app.ui.files import open_in_file_manager
from avispria.app.ui.jobs import run_job
from avispria.app.ui.layout import frame
from avispria.app.ui.pages.plan_form_parts import number, select_fit, text
from avispria.app.ui.state import STATE
from avispria.app.ui.widgets import PathField
from avispria.core.figure_spec import DPIS, RAMP_NAMES, WIDTHS_MM

FORMAT_TEXT = {
    "png": "PNG (image)",
    "tif": "TIFF (image, LZW)",
    "pdf": "PDF (vector text)",
    "svg": "SVG (vector, editable)",
}
RAMP_TEXT = {"": "The layer's own colours"} | {name: name.capitalize() for name in RAMP_NAMES}
ABOUT = (
    "Make a map image ready for a paper or a poster: choose the layer, the size in millimetres "
    "and the resolution, add a title, legend, north arrow, scale bar and grid, and look at the "
    "preview before saving. PDF and SVG keep the text and furniture as vectors, so a journal can "
    "scale them; SVG can be edited in Inkscape or Illustrator."
)


class FigureControls:
    def __init__(self) -> None:
        self.folder = PathField(
            "Maps folder",
            value=STATE.maps_folder,
            marker="figure-folder",
            hint="The folder that 'Make maps' saved to.",
            on_change=self.load_layers,
        )
        self.layer = ui.select({}, label="Map layer").classes("w-full").mark("figure-layer")
        with ui.row().classes("gap-2 items-start"):
            self.width = select_fit(
                ui.select(
                    [*WIDTHS_MM, CUSTOM], value="Journal, 2 columns (170 mm)", label="Width"
                ).mark("figure-width"),
                "Width",
            )
            self.custom = number("Width (mm)", 170, "figure-custom-width", min=20, max=600)
        self.custom.bind_visibility_from(self.width, "value", backward=lambda v: v == CUSTOM)
        with ui.row().classes("gap-2 items-center"):
            self.auto = ui.switch("Height fits the map", value=True).mark("figure-auto-height")
            self.height = number("Height (mm)", 120, "figure-height", min=20, max=600)
        self.height.bind_visibility_from(self.auto, "value", backward=lambda v: not v)
        with ui.row().classes("gap-2 items-start"):
            self.dpi = select_fit(
                ui.select({d: f"{d} dpi" for d in DPIS}, value=300, label="Resolution").mark(
                    "figure-dpi"
                ),
                "Resolution",
            )
            self.fmt = select_fit(
                ui.select(FORMAT_TEXT, value="png", label="Save as").mark("figure-format"),
                "Save as",
            )
            self.font = number("Text size (pt)", 8, "figure-font", min=5, max=24, step=0.5)
        self.title = text("Title (optional)", "figure-title")
        self.caption = (
            ui.textarea("Caption under the map (optional)")
            .props("outlined dense autogrow")
            .classes("w-full")
            .mark("figure-caption")
        )
        with ui.row().classes("gap-x-4 gap-y-0 flex-wrap"):
            self.legend = ui.switch("Legend or colour bar", value=True).mark("figure-legend")
            self.arrow = ui.switch("North arrow", value=True).mark("figure-arrow")
            self.scale = ui.switch("Scale bar", value=True).mark("figure-scale")
            self.grid = ui.switch("Coordinate grid", value=True).mark("figure-grid")
            self.crowns = ui.switch("Tree crown outlines", value=False).mark("figure-crowns")
        with ui.row().classes("gap-2 items-start"):
            self.ramp = select_fit(
                ui.select(RAMP_TEXT, value="", label="Colours").mark("figure-ramp"), "Colours"
            )
            self.low = number("From (blank: auto)", 0, "figure-low")
            self.high = number("To (blank: auto)", 0, "figure-high")
        self.low.value = None
        self.high.value = None
        self.size = ui.label("").classes("text-sm av-muted").mark("figure-size")
        for field in (self.width, self.custom, self.auto, self.height, self.dpi):
            field.on_value_change(self.show_size)

    def form(self) -> FigureForm:
        return FigureForm(
            folder=self.folder.value or "",
            layer=str(self.layer.value or ""),
            width_choice=str(self.width.value),
            custom_width_mm=self.custom.value,
            auto_height=bool(self.auto.value),
            height_mm=self.height.value,
            dpi=int(self.dpi.value or 300),
            fmt=str(self.fmt.value or "png"),
            title=self.title.value or "",
            caption=self.caption.value or "",
            legend=bool(self.legend.value),
            north_arrow=bool(self.arrow.value),
            scale_bar=bool(self.scale.value),
            grid=bool(self.grid.value),
            crowns=bool(self.crowns.value),
            ramp=str(self.ramp.value or ""),
            low=self.low.value,
            high=self.high.value,
            font_pt=float(self.font.value or 8),
        )

    def load_layers(self) -> None:
        choices = layer_choices(self.folder.value or "")
        self.layer.set_options(choices, value=next(iter(choices), None))
        self.show_size()

    def show_size(self) -> None:
        self.size.set_text(size_text(self.form()))


async def figure_page() -> None:
    with frame("Map images"):
        ui.label(ABOUT).classes("text-base")
        with ui.row().classes("w-full gap-4 items-start no-wrap av-figure-row"):
            with ui.card().classes("gap-3 av-figure-controls").mark("figure-controls"):
                controls = FigureControls()
                with ui.row().classes("gap-2"):
                    show = ui.button("Preview", icon="visibility").props("no-caps outline")
                    show.mark("figure-preview-button")
                    keep = ui.button("Save", icon="save").props("no-caps").mark("figure-save")
                result = ui.column().classes("w-full gap-1").mark("figure-result")
            with ui.card().classes("grow gap-2 av-figure-preview").mark("figure-preview"):
                ui.label("Preview").classes("font-bold")
                picture = ui.image("").classes("w-full").props("fit=contain").mark("figure-image")
                hint = ui.label("Press Preview to see the map image as it will be saved.")
                hint.classes("text-sm av-muted")
        controls.load_layers()

    def problem(text: str) -> None:
        result.clear()
        with result:
            ui.label(text).classes("av-problem-text font-medium").mark("figure-problem")

    async def look() -> None:
        hint.set_text("Drawing the preview...")
        outcome = await run_job(preview_job, controls.form())
        if not outcome.ok or outcome.value is None:
            hint.set_text("")
            problem(outcome.error or "The preview could not be drawn.")
            return
        result.clear()
        picture.set_source(outcome.value)
        hint.set_text("This is the layout that will be saved, at screen resolution.")

    async def store() -> None:
        result.clear()
        with result:
            ui.label("Saving at full resolution...").classes("text-sm")
        outcome = await run_job(save_job, controls.form())
        if not outcome.ok or outcome.value is None:
            problem(outcome.error or "The image was not saved.")
            return
        path = Path(outcome.value)
        result.clear()
        with result:
            ui.label(f"Saved: {path}").classes("font-medium break-all").mark("figure-saved")
            ui.button(
                "Open the folder",
                icon="folder_open",
                color="secondary",
                on_click=lambda: open_in_file_manager(path.parent),
            ).props("no-caps")

    show.on_click(look)
    keep.on_click(store)


__all__ = ["FIGURES_DIR", "figure_page"]
