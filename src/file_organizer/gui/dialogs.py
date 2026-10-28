"""Dialogs: conflict resolution."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from file_organizer.core import (
    ConflictKind, PlannedMove, Resolution, can_replace, files_identical,
    unique_destination,
)
from file_organizer.formatting import describe_file


def _file_card(title: str, path, name: str | None = None) -> QFrame:
    card = QFrame()
    card.setProperty("card", True)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(2)

    caption = QLabel(title.upper())
    caption.setProperty("muted", True)
    layout.addWidget(caption)

    label = QLabel(name or path.name)
    label.setProperty("subheading", True)
    label.setWordWrap(True)
    layout.addWidget(label)

    size, modified = describe_file(path)
    for text in (f"{size}", f"Modified {modified}", str(path.parent)):
        line = QLabel(text)
        line.setProperty("muted", True)
        line.setWordWrap(True)
        line.setToolTip(text)
        layout.addWidget(line)
    layout.addStretch(1)
    return card


class ConflictDialog(QDialog):
    """Ask the user what to do when a file is already at its destination."""

    def __init__(self, move: PlannedMove, position: int, total: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("File already exists")
        self.setModal(True)
        self.setMinimumWidth(620)

        self.resolution: Resolution | None = None
        self.apply_to_all = False
        self._replaceable = can_replace(move)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        if total > 1:
            counter = QLabel(f"Conflict {position} of {total}")
            counter.setProperty("muted", True)
            root.addWidget(counter)

        title = QLabel(
            "A file with this name is already there"
            if move.conflict is ConflictKind.EXISTS
            else "Two files would get the same name"
        )
        title.setProperty("heading", True)
        title.setStyleSheet("font-size: 20px;")
        root.addWidget(title)

        destination = QLabel(f"Destination folder: {move.destination.parent}")
        destination.setProperty("muted", True)
        destination.setWordWrap(True)
        root.addWidget(destination)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(_file_card("Incoming file", move.source))
        if move.conflict is ConflictKind.EXISTS and move.existing is not None:
            cards.addWidget(_file_card("Already in the folder", move.existing))
        root.addLayout(cards)

        if self._replaceable and files_identical(move.source, move.existing):
            note = QLabel("These two files have exactly the same content.")
            note.setProperty("badge", "ok")
            root.addWidget(note)
        elif move.conflict is ConflictKind.NAME_CLASH:
            note = QLabel(
                "Another file in this batch has the same name once letter "
                "case is ignored."
            )
            note.setProperty("badge", "warn")
            note.setWordWrap(True)
            root.addWidget(note)

        new_name = unique_destination(move.destination).name
        self._add_choice(
            root, "Keep both",
            f"The incoming file is renamed to “{new_name}”.",
            Resolution.KEEP_BOTH,
        )
        if self._replaceable:
            self._add_choice(
                root, "Replace",
                "The existing file is kept in a backup, so Undo brings it back.",
                Resolution.REPLACE,
            )
        self._add_choice(
            root, "Skip", "Leave the incoming file where it is.", Resolution.SKIP
        )

        footer = QHBoxLayout()
        self._all = QCheckBox("Do this for all remaining conflicts")
        self._all.setVisible(total - position > 0)
        footer.addWidget(self._all)
        footer.addStretch(1)
        cancel = QPushButton("Cancel everything")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        root.addLayout(footer)

    def _add_choice(self, layout, title: str, subtitle: str, resolution: Resolution) -> None:
        button = QPushButton()
        button.setProperty("choice", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        inner = QVBoxLayout(button)
        inner.setContentsMargins(14, 8, 14, 8)
        inner.setSpacing(1)
        heading = QLabel(title)
        heading.setProperty("subheading", True)
        detail = QLabel(subtitle)
        detail.setProperty("muted", True)
        for label in (heading, detail):  # let clicks reach the button
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            inner.addWidget(label)
        button.setMinimumHeight(64)
        button.clicked.connect(lambda: self._choose(resolution))
        layout.addWidget(button)

    def _choose(self, resolution: Resolution) -> None:
        self.resolution = resolution
        self.apply_to_all = self._all.isChecked()
        self.accept()
