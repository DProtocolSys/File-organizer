"""Generate the application icons in ``assets/`` (needs: pip install pillow).

    python scripts/make_icons.py

Produces ``icon.png`` (1024 px), ``icon.ico`` (Windows, 16-256 px) and
``icon.icns`` (macOS). The design comes from ``file_organizer/icon_design.py``,
the same data the window icon is drawn from.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from file_organizer import icon_design as design  # noqa: E402

ASSETS = ROOT / "assets"
SIZE = 1024
SCALE = SIZE / design.GRID


def _box(x: float, y: float, w: float, h: float) -> tuple[float, ...]:
    return (x * SCALE, y * SCALE, (x + w) * SCALE - 1, (y + h) * SCALE - 1)


def draw_icon() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x, y, w, h, radius = design.BACKGROUND
    draw.rounded_rectangle(_box(x, y, w, h), radius * SCALE, fill=design.BACKGROUND_COLOR)
    for x, y, w, h, radius, color in design.SHAPES:
        draw.rounded_rectangle(_box(x, y, w, h), radius * SCALE, fill=color)
    return image


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    image = draw_icon()
    image.save(ASSETS / "icon.png")
    image.save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    image.save(ASSETS / "icon.icns")
    print("Icons written to", ASSETS)


if __name__ == "__main__":
    main()
