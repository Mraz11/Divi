# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Make every logo file from the founder's logo (``branding/logo-source.png``).

The source is a transparent square PNG: green (vegetation), yellow (agriculture) and blue-grey
(urban) rings around a slate drone. On a dark page the slate parts (the drone's frame, rotors and
hub, about 30% value) would disappear, so the dark-mode variant lifts exactly those pixels to a
light slate, keeping their shading and edges; the three colours stay as designed.

Writes the sizes the window, the browser tab and the phone's home screen need:

    branding/logo.png, logo-dark.png            1024 px, the reference copies
    src/avispria/app/ui/assets/logo*.png        256 px (shown at 40 and 112 px, sharp on HiDPI)
    src/avispria/app/ui/assets/favicon.png      64 px
    field-page/img/logo*.png                    256 px
    field-page/icons/*                          home-screen and tab icons

Run ``python scripts/make_branding.py`` after changing the source. Needs numpy and Pillow.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "branding" / "logo-source.png"
APP_ASSETS = ROOT / "src" / "avispria" / "app" / "ui" / "assets"
PHONE = ROOT / "field-page"
LIGHT_SLATE = np.array([201, 211, 216], dtype=np.float32)  # the drone on a dark page
MIST, NIGHT = (244, 247, 248), (11, 16, 19)  # page colours of theme.py


def load() -> Image.Image:
    image = Image.open(SOURCE).convert("RGBA")
    box = image.getbbox()  # crop to the logo, then centre it on a square
    if box:
        image = image.crop(box)
    side = max(image.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return square


def dark_variant(image: Image.Image) -> Image.Image:
    """The slate parts lifted to light slate, shading kept; the colours untouched."""
    a = np.asarray(image).astype(np.float32)
    rgb = a[..., :3] / 255
    value = rgb.max(axis=-1)
    low = rgb.min(axis=-1)
    saturation = np.where(value > 0, (value - low) / np.maximum(value, 1e-6), 0)
    slate = (value < 0.5) & (saturation < 0.4) & (a[..., 3] > 0)
    shade = np.clip(value / 0.40, 0.75, 1.15)[..., None]  # keep the drone's light and dark sides
    lifted = np.clip(LIGHT_SLATE * shade, 0, 255)
    a[..., :3] = np.where(slate[..., None], lifted, a[..., :3])
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def sized(image: Image.Image, px: int) -> Image.Image:
    """Resized; the faint haze resampling leaves around the edge (alpha below 8) is cleared."""
    out = np.asarray(image.resize((px, px), Image.LANCZOS)).copy()
    out[out[..., 3] < 8] = 0
    return Image.fromarray(out, "RGBA")


def small(image: Image.Image, px: int) -> Image.Image:
    """A screen-size copy with a 256-colour palette: loads on every visit, so it must stay light."""
    return sized(image, px).quantize(
        256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE
    )


def on_background(
    image: Image.Image, px: int, colour: tuple[int, int, int], fill: float
) -> Image.Image:
    """The logo at ``fill`` of a square of ``colour`` (home-screen icons need a solid tile)."""
    tile = Image.new("RGBA", (px, px), (*colour, 255))
    inner = sized(image, round(px * fill))
    offset = (px - inner.width) // 2
    tile.alpha_composite(inner, (offset, offset))
    return tile.convert("RGB")


def main() -> None:
    light = load()
    dark = dark_variant(light)
    sized(light, 1024).save(ROOT / "branding" / "logo.png", optimize=True)
    sized(dark, 1024).save(ROOT / "branding" / "logo-dark.png", optimize=True)
    small(light, 256).save(APP_ASSETS / "logo.png", optimize=True)
    small(dark, 256).save(APP_ASSETS / "logo-dark.png", optimize=True)
    small(light, 64).save(APP_ASSETS / "favicon.png", optimize=True)
    small(light, 256).save(PHONE / "img" / "logo.png", optimize=True)
    small(dark, 256).save(PHONE / "img" / "logo-dark.png", optimize=True)
    icons = PHONE / "icons"
    sized(light, 64).save(icons / "favicon.png", optimize=True)
    on_background(light, 180, MIST, 0.86).save(icons / "apple-touch-icon.png", optimize=True)
    sized(light, 192).save(icons / "icon-192.png", optimize=True)  # round logo, clear corners
    sized(light, 512).save(icons / "icon-512.png", optimize=True)
    # maskable: the system may cut the icon to a circle; the safe zone is the middle 80%
    on_background(light, 512, MIST, 0.72).save(icons / "icon-maskable-512.png", optimize=True)
    print("logo files written")


if __name__ == "__main__":
    main()
