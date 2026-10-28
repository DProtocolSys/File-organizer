"""Build a standalone, double-clickable application with PyInstaller.

    pip install ".[build]"
    python scripts/build_executable.py

Output goes to ``dist/``:
  * Windows: ``dist/FileOrganizer.exe``      (single file, with icon)
  * Linux:   ``dist/FileOrganizer``          (single file)
  * macOS:   ``dist/FileOrganizer.app``      (application bundle, with icon)

PyInstaller does not cross-compile: run this script on each operating system
you want to ship for (the GitHub workflow in ``.github/workflows/release.yml``
does exactly that). Icons live in ``assets/`` and are regenerated with
``python scripts/make_icons.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_command(platform: str = sys.platform) -> list[str]:
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed",                       # no console window
        "--name", "FileOrganizer",
        "--paths", str(ROOT / "src"),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    if platform == "win32":
        command += ["--icon", str(ROOT / "assets" / "icon.ico")]
    elif platform == "darwin":
        command += ["--icon", str(ROOT / "assets" / "icon.icns")]
    # A single file is convenient on Windows/Linux; macOS apps are bundles.
    if platform != "darwin":
        command.append("--onefile")
    command.append(str(ROOT / "packaging" / "launcher.py"))
    return command


def main() -> int:
    command = build_command()
    print("Running:", " ".join(command))
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
