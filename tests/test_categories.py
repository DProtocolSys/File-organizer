"""Tests for the file categorization module."""

import pytest

from file_organizer.categories import FILE_CATEGORIES, get_category


@pytest.mark.parametrize(
    ("filename", "category"),
    [
        ("photo.jpg", "Images"),
        ("photo.JPG", "Images"),
        ("report.PDF", "Documents"),
        ("budget.xlsx", "Spreadsheets"),
        ("deck.pptx", "Presentations"),
        ("song.mp3", "Audio"),
        ("movie.mkv", "Videos"),
        ("script.py", "Code"),
        ("setup.exe", "Installers"),
        ("book.epub", "Ebooks"),
        ("font.woff2", "Fonts"),
        ("my.holiday.photo.png", "Images"),  # only the last extension counts
        ("archive.tar.gz", "Archives"),
    ],
)
def test_known_extensions(filename, category):
    assert get_category(filename) == category


@pytest.mark.parametrize(
    "filename",
    ["file.unknown", "README", ".gitignore", ".jpg", "trailingdot.", ""],
)
def test_unknown_names_return_none(filename):
    assert get_category(filename) is None


def test_no_extension_belongs_to_two_categories():
    seen: dict[str, str] = {}
    for category, extensions in FILE_CATEGORIES.items():
        for extension in extensions:
            assert extension == extension.lower()
            assert extension.startswith(".")
            assert extension not in seen, (
                f"{extension} is in {seen[extension]} and {category}"
            )
            seen[extension] = category
