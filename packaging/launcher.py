"""Entry point used by PyInstaller to build the standalone application."""

from file_organizer.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
