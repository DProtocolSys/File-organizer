# Third-party notices

File Organizer itself is released under the MIT License (see `LICENSE`).
The standalone executables additionally bundle the following components, which
keep their own licenses.

| Component | Used for | License |
|-----------|----------|---------|
| [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/) and the Qt libraries | Graphical interface | LGPL-3.0 (GPL-3.0 / commercial also available) |
| [PyInstaller](https://pyinstaller.org/) | Building the executables only | GPL-2.0 with a special exception that allows the bundled application to use any license |
| [Pillow](https://python-pillow.org/) | Generating the icons (`scripts/make_icons.py`, development only, not bundled) | HPND |

**Qt / PySide6 (LGPL-3.0).** The executables are built from unmodified PySide6
and Qt libraries, which are dynamically linked and can be replaced by the user.
You can obtain their source code and the full license text at
<https://www.qt.io/download-open-source> and
<https://www.gnu.org/licenses/lgpl-3.0.html>.

This file is provided for information and is not legal advice.
