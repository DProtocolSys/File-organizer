"""Small human-readable formatting helpers shared by the CLI and the GUI."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def format_size(size: int) -> str:
    """``1536`` -> ``'1.5 KB'``."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def describe_file(path: str | Path) -> tuple[str, str]:
    """Return ``(size, modification date)`` as display strings."""
    try:
        info = os.stat(path)
    except OSError:
        return "unknown", "unknown"
    modified = datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M")
    return format_size(info.st_size), modified
