"""File categories and extension lookup."""

from __future__ import annotations

import os

#: Category name -> extensions (lower-case, with leading dot).
#: Dictionary order is the display order in the user interface.
FILE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Images": (
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif",
        ".svg", ".ico", ".heic", ".heif", ".raw", ".cr2", ".nef", ".arw",
    ),
    "Videos": (
        ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm", ".m4v", ".flv",
        ".mpg", ".mpeg", ".3gp",
    ),
    "Audio": (
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
        ".aiff", ".mid", ".midi",
    ),
    "Documents": (
        ".doc", ".docx", ".pdf", ".txt", ".odt", ".rtf", ".md", ".tex",
        ".pages",
    ),
    "Spreadsheets": (".xls", ".xlsx", ".csv", ".ods", ".tsv", ".numbers"),
    "Presentations": (".ppt", ".pptx", ".odp", ".key"),
    "Ebooks": (".epub", ".mobi", ".azw3", ".djvu"),
    "Archives": (
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".zst",
    ),
    "Code": (
        ".py", ".ipynb", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".h",
        ".cpp", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt",
        ".html", ".css", ".json", ".xml", ".yaml", ".yml", ".toml", ".sql",
        ".sh", ".bat", ".ps1",
    ),
    "Fonts": (".ttf", ".otf", ".woff", ".woff2"),
    "Installers": (
        ".exe", ".msi", ".msix", ".deb", ".rpm", ".appimage", ".dmg", ".pkg",
        ".apk", ".iso",
    ),
}

#: Name of the optional catch-all category (see ``include_unknown``).
OTHER_CATEGORY = "Other"


def _build_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for category, extensions in FILE_CATEGORIES.items():
        for extension in extensions:
            if extension in lookup:
                raise ValueError(
                    f"Extension {extension!r} is listed in both "
                    f"{lookup[extension]!r} and {category!r}"
                )
            lookup[extension] = category
    return lookup


# Built once at import time: each lookup is a single O(1) dict access.
_EXTENSION_TO_CATEGORY: dict[str, str] = _build_lookup()


def get_category(filename: str) -> str | None:
    """Return the category of ``filename``, or ``None`` if it is unknown.

    The comparison is case-insensitive. Only the last extension counts
    (``archive.tar.gz`` is an archive). Dotfiles such as ``.gitignore`` and
    names ending with a dot have no extension and return ``None``.
    """
    extension = os.path.splitext(filename)[1].lower()
    return _EXTENSION_TO_CATEGORY.get(extension)
