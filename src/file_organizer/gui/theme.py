"""Light and dark themes (follows the operating-system setting)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

LIGHT = {
    "bg": "#F5F6F8", "surface": "#FFFFFF", "border": "#E2E5EA",
    "text": "#1B1F27", "muted": "#6B7280", "primary": "#4F46E5",
    "primary_hover": "#4338CA", "on_primary": "#FFFFFF",
    "soft": "#EEF2FF", "row_alt": "#FAFBFC", "warn_bg": "#FEF3C7",
    "warn_text": "#92400E", "ok_bg": "#DCFCE7", "ok_text": "#166534",
    "danger": "#DC2626", "header": "#F0F2F5", "dash": "#C3C9D4",
}
DARK = {
    "bg": "#0F1218", "surface": "#171B24", "border": "#2A303C",
    "text": "#E8EAF0", "muted": "#9AA3B2", "primary": "#818CF8",
    "primary_hover": "#A5B4FC", "on_primary": "#0F1218",
    "soft": "#222850", "row_alt": "#1A1F29", "warn_bg": "#3B2F0B",
    "warn_text": "#FCD34D", "ok_bg": "#10301D", "ok_text": "#86EFAC",
    "danger": "#F87171", "header": "#1D222D", "dash": "#3C4455",
}

#: Accent colour of each category (used for the dots and destination labels).
CATEGORY_COLORS = {
    "Images": "#EC4899", "Videos": "#F97316", "Audio": "#A855F7",
    "Documents": "#3B82F6", "Spreadsheets": "#22C55E",
    "Presentations": "#EAB308", "Ebooks": "#14B8A6", "Archives": "#78716C",
    "Code": "#6366F1", "Fonts": "#06B6D4", "Installers": "#EF4444",
    "Other": "#94A3B8",
}


def category_color(category: str) -> str:
    return CATEGORY_COLORS.get(category, "#94A3B8")


def build_stylesheet(t: dict[str, str]) -> str:
    return f"""
* {{ font-size: 13px; }}
QMainWindow, QDialog, QWidget#page {{ background: {t['bg']}; color: {t['text']}; }}
QLabel {{ color: {t['text']}; background: transparent; }}
QLabel[muted="true"] {{ color: {t['muted']}; }}
QLabel[heading="true"] {{ font-size: 26px; font-weight: 700; }}
QLabel[subheading="true"] {{ font-size: 15px; font-weight: 600; }}
QLabel[badge="warn"] {{ background: {t['warn_bg']}; color: {t['warn_text']};
    border-radius: 8px; padding: 8px 12px; }}
QLabel[badge="ok"] {{ background: {t['ok_bg']}; color: {t['ok_text']};
    border-radius: 8px; padding: 8px 12px; }}

QFrame[card="true"] {{ background: {t['surface']}; border: 1px solid {t['border']};
    border-radius: 12px; }}
QFrame#dropzone {{ background: {t['surface']}; border: 2px dashed {t['dash']};
    border-radius: 16px; }}
QFrame#dropzone[hover="true"] {{ border-color: {t['primary']}; background: {t['soft']}; }}

QPushButton {{ background: {t['surface']}; color: {t['text']};
    border: 1px solid {t['border']}; border-radius: 8px; padding: 8px 16px; }}
QPushButton:hover {{ border-color: {t['primary']}; }}
QPushButton:disabled {{ color: {t['muted']}; background: {t['bg']}; }}
QPushButton[primary="true"] {{ background: {t['primary']}; color: {t['on_primary']};
    border: none; font-weight: 600; padding: 10px 22px; }}
QPushButton[primary="true"]:hover {{ background: {t['primary_hover']}; }}
QPushButton[primary="true"]:disabled {{ background: {t['border']}; color: {t['muted']}; }}
QPushButton[flat="true"] {{ border: none; background: transparent; color: {t['primary']};
    padding: 4px 8px; }}
QPushButton[choice="true"] {{ text-align: left; padding: 12px 16px; }}
QPushButton[choice="true"]:hover {{ background: {t['soft']}; }}

QLineEdit {{ background: {t['surface']}; color: {t['text']};
    border: 1px solid {t['border']}; border-radius: 8px; padding: 7px 10px; }}
QLineEdit:focus {{ border-color: {t['primary']}; }}
QCheckBox {{ color: {t['text']}; spacing: 8px; }}

QTableView {{ background: {t['surface']}; alternate-background-color: {t['row_alt']};
    color: {t['text']}; border: 1px solid {t['border']}; border-radius: 10px;
    gridline-color: transparent; selection-background-color: {t['soft']};
    selection-color: {t['text']}; }}
QTableView::item {{ padding: 0 10px; }}
QHeaderView::section {{ background: {t['header']}; color: {t['muted']}; border: none;
    padding: 8px; font-weight: 600; }}
QListWidget {{ background: {t['surface']}; color: {t['text']};
    border: 1px solid {t['border']}; border-radius: 10px; padding: 4px; outline: 0; }}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {t['soft']}; }}
QListWidget::item:selected {{ background: {t['soft']}; color: {t['text']}; }}

QProgressBar {{ background: {t['border']}; border: none; border-radius: 5px;
    height: 10px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {t['primary']}; border-radius: 5px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""


def _is_dark(app: QApplication) -> bool:
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def apply_theme(app: QApplication) -> None:
    """Apply the theme matching the system and keep following changes."""

    def refresh() -> None:
        app.setStyleSheet(build_stylesheet(DARK if _is_dark(app) else LIGHT))

    refresh()
    app.styleHints().colorSchemeChanged.connect(lambda *_: refresh())


def current_tokens(app: QApplication) -> dict[str, str]:
    return DARK if _is_dark(app) else LIGHT
