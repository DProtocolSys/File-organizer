"""Table model of the planned moves."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor

from file_organizer.core import ConflictKind, PlannedMove
from file_organizer.formatting import format_size
from file_organizer.gui.theme import category_color

COLUMNS = ("File", "Destination", "Size", "Status")
SORT_ROLE = Qt.ItemDataRole.UserRole

_STATUS = {
    None: "Ready",
    ConflictKind.EXISTS: "Already exists",
    ConflictKind.NAME_CLASH: "Name clash",
}


class PlanModel(QAbstractTableModel):
    """Planned moves, each with a check box so the user can exclude files."""

    selection_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._moves: list[PlannedMove] = []
        self._checked: list[bool] = []

    # -- data ---------------------------------------------------------------
    def set_moves(self, moves: list[PlannedMove]) -> None:
        self.beginResetModel()
        self._moves = list(moves)
        self._checked = [True] * len(self._moves)
        self.endResetModel()
        self.selection_changed.emit()

    def selected_moves(self) -> list[PlannedMove]:
        return [m for m, on in zip(self._moves, self._checked) if on]

    def category_counts(self) -> Counter:
        return Counter(m.category for m in self._moves)

    def checked_category_counts(self) -> Counter:
        return Counter(m.category for m, on in zip(self._moves, self._checked) if on)

    def set_category_checked(self, category: str, checked: bool) -> None:
        for row, move in enumerate(self._moves):
            if move.category == category:
                self._checked[row] = checked
        self._refresh_checks()

    def set_all_checked(self, checked: bool) -> None:
        self._checked = [checked] * len(self._moves)
        self._refresh_checks()

    def _refresh_checks(self) -> None:
        if self._moves:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._moves) - 1, 0),
                [Qt.ItemDataRole.CheckStateRole],
            )
        self.selection_changed.emit()

    # -- QAbstractTableModel -------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._moves)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        move = self._moves[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.CheckStateRole and column == 0:
            return Qt.CheckState.Checked if self._checked[index.row()] else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                move.source.name,
                f"{move.category}/",
                format_size(move.size),
                _STATUS[move.conflict],
            )[column]
        if role == SORT_ROLE:
            return (move.source.name.lower(), move.category, move.size,
                    move.conflict is not None)[column]
        if role == Qt.ItemDataRole.ForegroundRole:
            if column == 1:
                return QColor(category_color(move.category))
            if column == 3 and move.conflict is not None:
                return QColor("#D97706")
        if role == Qt.ItemDataRole.TextAlignmentRole and column == 2:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 3 and move.conflict is not None:
                return "You will be asked what to do with this file."
            return str(move.source)
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.isValid() and index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            self._checked[index.row()] = Qt.CheckState(value) == Qt.CheckState.Checked
            self.dataChanged.emit(index, index, [role])
            self.selection_changed.emit()
            return True
        return False
