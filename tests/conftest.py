"""Shared pytest configuration."""

import os

# Run Qt without a display (CI, servers). Must be set before Qt is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
