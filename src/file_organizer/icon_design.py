"""Single source of truth for the application icon.

The icon is described on a 128 x 128 grid as plain data, so the window icon
(``gui/app.py``, drawn with Qt) and the executable icons
(``scripts/make_icons.py``, drawn with Pillow) always look identical.
"""

from __future__ import annotations

GRID = 128

BACKGROUND_COLOR = "#4F46E5"
#: (x, y, width, height, corner radius) of the rounded background square.
BACKGROUND = (4, 4, 120, 120, 28)

_WHITE = "#FFFFFF"
_TINT = "#C7D2FE"


def _cards() -> list[tuple[int, int, int, int, int, str]]:
    """Three columns of cards: files sorted into categories."""
    cards = []
    for x, count in ((19, 2), (51, 3), (83, 2)):
        for row in range(count):
            color = _WHITE if row == 0 else _TINT
            cards.append((x, 28 + row * 26, 26, 20, 6, color))
    return cards


#: ``(x, y, width, height, corner radius, color)`` drawn over the background.
SHAPES = _cards()
