"""Graphical interface (requires the optional PySide6 dependency)."""

from __future__ import annotations

import sys


def main() -> int:
    """Start the graphical application."""
    try:
        from file_organizer.gui.app import run
    except ImportError as error:  # PySide6 missing
        print(
            "The graphical interface needs PySide6.\n"
            'Install it with:  pip install "file-organizer[gui]"\n'
            f"({error})",
            file=sys.stderr,
        )
        return 1
    return run()
