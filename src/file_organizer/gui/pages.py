"""The four screens of the application."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
    QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from file_organizer.core import PlannedMove
from file_organizer.gui.models import SORT_ROLE, PlanModel
from file_organizer.gui.theme import category_color


def _label(text: str = "", **props) -> QLabel:
    label = QLabel(text)
    for key, value in props.items():
        label.setProperty(key, value)
    return label


def _button(text: str, *, primary: bool = False, flat: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        button.setProperty("primary", True)
    if flat:
        button.setProperty("flat", True)
    return button


def _dot_icon(color: str) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, 12, 12)
    painter.end()
    return QIcon(pixmap)


def _page() -> QWidget:
    widget = QWidget()
    widget.setObjectName("page")
    return widget


# --------------------------------------------------------------------------- #
class DropZone(QFrame):
    """Large target: drop a folder on it or click to browse."""

    folder_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(190)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = _label("📁")
        icon.setStyleSheet("font-size: 44px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = _label("Drop a folder here", subheading=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = _label("or click to choose one", muted=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for widget in (icon, title, hint):
            layout.addWidget(widget)

    def _set_hover(self, value: bool) -> None:
        self.setProperty("hover", value)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            folder = QFileDialog.getExistingDirectory(self, "Choose a folder to organize")
            if folder:
                self.folder_selected.emit(folder)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hover(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_hover(False)

    def dropEvent(self, event) -> None:
        self._set_hover(False)
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file():
                path = path.parent
            if path.is_dir():
                self.folder_selected.emit(str(path))
                return


class WelcomePage(QWidget):
    folder_chosen = Signal(str)

    def __init__(self, settings: QSettings) -> None:
        super().__init__()
        self.setObjectName("page")
        self._settings = settings

        outer = QVBoxLayout(self)
        outer.setContentsMargins(48, 40, 48, 32)
        outer.addStretch(1)

        column = QVBoxLayout()
        column.setSpacing(14)
        column.addWidget(_label("File Organizer", heading=True))
        column.addWidget(_label(
            "Tidy a folder in one click. Nothing is deleted and every run "
            "can be undone.", muted=True))
        column.addSpacing(8)
        zone = DropZone()
        zone.folder_selected.connect(self.folder_chosen)
        column.addWidget(zone)

        self._recent_box = QVBoxLayout()
        self._recent_box.setSpacing(2)
        column.addLayout(self._recent_box)

        holder = QHBoxLayout()
        holder.addStretch(1)
        inner = QWidget()
        inner.setLayout(column)
        inner.setMaximumWidth(640)
        inner.setMinimumWidth(520)
        holder.addWidget(inner, 10)
        holder.addStretch(1)
        outer.addLayout(holder)
        outer.addStretch(2)
        self.refresh_recent()

    def remember(self, folder: str) -> None:
        recent = [f for f in self.recent() if f != folder]
        self._settings.setValue("recent", [folder, *recent][:5])
        self.refresh_recent()

    def recent(self) -> list[str]:
        value = self._settings.value("recent", [])
        if isinstance(value, str):
            value = [value]
        return [f for f in (value or []) if Path(f).is_dir()]

    def forget(self, folder: str) -> None:
        """Remove one folder from the recent list (the folder itself is untouched)."""
        remaining = [f for f in self.recent() if f != folder]
        if remaining:
            self._settings.setValue("recent", remaining)
        else:
            self._settings.remove("recent")
        self.refresh_recent()

    def clear_recent(self) -> None:
        """Empty the recent list. Only this display list is affected."""
        self._settings.remove("recent")
        self.refresh_recent()

    def refresh_recent(self) -> None:
        self._delete_layout(self._recent_box)
        recent = self.recent()
        if not recent:
            return  # nothing to show: the whole section disappears

        header = QHBoxLayout()
        header.addWidget(_label("Recent folders", muted=True))
        header.addStretch(1)
        clear = _button("Clear", flat=True)
        clear.setToolTip("Forget the recent folders (your files are not touched)")
        clear.clicked.connect(self.clear_recent)
        header.addWidget(clear)
        self._recent_box.addLayout(header)

        for folder in recent:
            row = QHBoxLayout()
            button = _button(folder, flat=True)
            button.setStyleSheet("text-align: left;")
            button.clicked.connect(lambda _=False, f=folder: self.folder_chosen.emit(f))
            row.addWidget(button, 1)
            remove = _button("✕", flat=True)
            remove.setToolTip("Remove from this list")
            remove.clicked.connect(lambda _=False, f=folder: self.forget(f))
            row.addWidget(remove)
            self._recent_box.addLayout(row)

    @staticmethod
    def _delete_layout(layout) -> None:
        """Empty a layout. Widgets are detached at once: ``deleteLater`` alone
        would leave them painted in the old place until the next event-loop turn."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
            elif item.layout():
                WelcomePage._delete_layout(item.layout())


# --------------------------------------------------------------------------- #
class ReviewPage(QWidget):
    back_requested = Signal()
    reload_requested = Signal()
    organize_requested = Signal()
    undo_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page")
        self._syncing = False
        self.model = PlanModel(self)
        self.model.selection_changed.connect(self._on_selection_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        back = _button("←  Change folder", flat=True)
        back.clicked.connect(self.back_requested)
        header.addWidget(back)
        header.addStretch(1)
        layout.addLayout(header)
        self._title = _label("", heading=True)
        self._title.setStyleSheet("font-size: 22px;")
        layout.addWidget(self._title)
        self._path = _label("", muted=True)
        layout.addWidget(self._path)

        options = QHBoxLayout()
        self.unknown_box = QCheckBox("Move unrecognized files into “Other”")
        self.hidden_box = QCheckBox("Include hidden files")
        for box in (self.unknown_box, self.hidden_box):
            box.toggled.connect(lambda _=False: self.reload_requested.emit())
            options.addWidget(box)
        options.addStretch(1)
        layout.addLayout(options)

        # Undo banner
        self._banner = QFrame()
        self._banner.setProperty("card", True)
        banner = QHBoxLayout(self._banner)
        banner.addWidget(_label("This folder was organized before."))
        banner.addStretch(1)
        undo = _button("Undo last run")
        undo.clicked.connect(self.undo_requested)
        banner.addWidget(undo)
        self._banner.hide()
        layout.addWidget(self._banner)

        # Body
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)
        self._stack.addWidget(self._centered("Scanning folder…"))
        self._stack.addWidget(self._build_content())
        self._empty = self._centered("")
        self._stack.addWidget(self._empty)

        # Footer
        footer = QHBoxLayout()
        self._summary = _label("", muted=True)
        footer.addWidget(self._summary)
        footer.addStretch(1)
        self._go = _button("Organize", primary=True)
        self._go.clicked.connect(self.organize_requested)
        footer.addWidget(self._go)
        layout.addLayout(footer)

    # -- construction ---------------------------------------------------------
    def _centered(self, text: str) -> QWidget:
        holder = QWidget()
        box = QVBoxLayout(holder)
        label = _label(text, muted=True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        box.addWidget(label)
        holder.label = label  # type: ignore[attr-defined]
        return holder

    def _build_content(self) -> QWidget:
        content = QWidget()
        row = QHBoxLayout(content)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)

        side = QVBoxLayout()
        tools = QHBoxLayout()
        tools.addWidget(_label("Folders to create", subheading=True))
        tools.addStretch(1)
        select_all = _button("All", flat=True)
        select_none = _button("None", flat=True)
        select_all.clicked.connect(lambda: self.model.set_all_checked(True))
        select_none.clicked.connect(lambda: self.model.set_all_checked(False))
        tools.addWidget(select_all)
        tools.addWidget(select_none)
        side.addLayout(tools)
        self._categories = QListWidget()
        self._categories.setFixedWidth(230)
        self._categories.itemChanged.connect(self._on_category_toggled)
        side.addWidget(self._categories, 1)
        row.addLayout(side)

        main = QVBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search files…")
        self._search.setClearButtonEnabled(True)
        main.addWidget(self._search)

        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self.model)
        self._proxy.setSortRole(SORT_ROLE)
        self._proxy.setFilterKeyColumn(0)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._search.textChanged.connect(self._proxy.setFilterFixedString)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setSelectionMode(QTableView.SelectionMode.NoSelection)
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._table.setWordWrap(False)
        self._table.verticalHeader().hide()
        self._table.verticalHeader().setDefaultSectionSize(34)
        head = self._table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            head.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        main.addWidget(self._table, 1)
        row.addLayout(main, 1)
        return content

    # -- public API -----------------------------------------------------------
    def set_folder(self, folder: str, has_history: bool) -> None:
        self._title.setText(Path(folder).name or folder)
        self._path.setText(folder)
        self._banner.setVisible(has_history)

    def show_scanning(self) -> None:
        self._stack.setCurrentIndex(0)
        self._go.setEnabled(False)
        self._summary.setText("")

    def show_plan(self, moves: list[PlannedMove]) -> None:
        self._search.clear()
        self.model.set_moves(moves)
        self._populate_categories()
        if moves:
            self._stack.setCurrentIndex(1)
        else:
            self._empty.label.setText(  # type: ignore[attr-defined]
                "Nothing to organize here.\nThis folder has no loose files "
                "of a known type.")
            self._stack.setCurrentIndex(2)
        self._on_selection_changed()

    def show_error(self, message: str) -> None:
        self._empty.label.setText(message)  # type: ignore[attr-defined]
        self._stack.setCurrentIndex(2)
        self._go.setEnabled(False)

    def selected_moves(self) -> list[PlannedMove]:
        return self.model.selected_moves()

    # -- internals ------------------------------------------------------------
    def _populate_categories(self) -> None:
        self._syncing = True
        self._categories.clear()
        for category, count in sorted(self.model.category_counts().items()):
            item = QListWidgetItem(_dot_icon(category_color(category)), f"{category}  ({count})")
            item.setData(Qt.ItemDataRole.UserRole, category)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._categories.addItem(item)
        self._syncing = False

    def _on_category_toggled(self, item: QListWidgetItem) -> None:
        if self._syncing:
            return
        state = item.checkState()
        if state != Qt.CheckState.PartiallyChecked:
            self.model.set_category_checked(
                item.data(Qt.ItemDataRole.UserRole), state == Qt.CheckState.Checked)

    def _on_selection_changed(self) -> None:
        totals = self.model.category_counts()
        checked = self.model.checked_category_counts()

        self._syncing = True
        for index in range(self._categories.count()):
            item = self._categories.item(index)
            category = item.data(Qt.ItemDataRole.UserRole)
            on, total = checked.get(category, 0), totals[category]
            item.setCheckState(
                Qt.CheckState.Unchecked if on == 0
                else Qt.CheckState.Checked if on == total
                else Qt.CheckState.PartiallyChecked)
        self._syncing = False

        selected = self.model.selected_moves()
        conflicts = sum(1 for move in selected if move.conflict)
        parts = [f"{len(selected)} of {sum(totals.values())} files selected"]
        if conflicts:
            parts.append(f"{conflicts} conflict{'s' if conflicts > 1 else ''} — you will be asked what to do")
        self._summary.setText("  ·  ".join(parts))
        self._go.setText(f"Organize {len(selected)} file{'s' if len(selected) != 1 else ''}")
        self._go.setEnabled(bool(selected))


# --------------------------------------------------------------------------- #
class ProgressPage(QWidget):
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 40, 80, 40)
        layout.addStretch(1)
        self._title = _label("Organizing…", heading=True)
        self._title.setStyleSheet("font-size: 22px;")
        layout.addWidget(self._title)
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        layout.addWidget(self._bar)
        self._detail = _label("", muted=True)
        layout.addWidget(self._detail)
        row = QHBoxLayout()
        self._cancel = _button("Cancel")
        self._cancel.clicked.connect(self._on_cancel)
        row.addWidget(self._cancel)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(2)

    def start(self, title: str, cancellable: bool = True) -> None:
        self._title.setText(title)
        self._bar.setRange(0, 0)  # busy indicator until the first update
        self._detail.setText("")
        self._cancel.setText("Cancel")
        self._cancel.setEnabled(cancellable)
        self._cancel.setVisible(cancellable)

    def update_progress(self, done: int, total: int, label: str) -> None:
        self._bar.setRange(0, max(total, 1))
        self._bar.setValue(done)
        self._detail.setText(f"{done} of {total}  ·  {label}")

    def _on_cancel(self) -> None:
        self._cancel.setEnabled(False)
        self._cancel.setText("Cancelling — restoring files…")
        self.cancel_requested.emit()


# --------------------------------------------------------------------------- #
class ResultPage(QWidget):
    open_folder_requested = Signal()
    undo_requested = Signal()
    again_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 40, 80, 40)
        layout.addStretch(1)

        self._icon = _label("✓")
        self._icon.setStyleSheet("font-size: 48px; color: #22C55E;")
        layout.addWidget(self._icon)
        self._title = _label("", heading=True)
        self._title.setStyleSheet("font-size: 24px;")
        layout.addWidget(self._title)
        self._details = _label("", muted=True)
        self._details.setTextFormat(Qt.TextFormat.RichText)
        self._details.setWordWrap(True)
        layout.addWidget(self._details)
        layout.addSpacing(12)

        row = QHBoxLayout()
        self._open = _button("Open folder", primary=True)
        self._open.clicked.connect(self.open_folder_requested)
        self._undo = _button("Undo")
        self._undo.clicked.connect(self.undo_requested)
        again = _button("Organize another folder")
        again.clicked.connect(self.again_requested)
        for button in (self._open, self._undo, again):
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(2)

    def show_success(self, counts: dict[str, int], can_undo: bool, note: str = "") -> None:
        total = sum(counts.values())
        self._icon.setText("✓")
        self._icon.setStyleSheet("font-size: 48px; color: #22C55E;")
        self._title.setText(f"{total} file{'s' if total != 1 else ''} organized")
        lines = [
            f"<span style='color:{category_color(c)}'>●</span>&nbsp; {c} — {n}"
            for c, n in sorted(counts.items())
        ]
        if note:
            lines.append(f"<br>{note}")
        self._details.setText(
            "<div style='line-height:170%; font-size:14px'>" + "<br>".join(lines) + "</div>")
        self._undo.setVisible(can_undo)
        self._open.setVisible(True)

    def show_error(self, message: str) -> None:
        self._icon.setText("⚠")
        self._icon.setStyleSheet("font-size: 48px; color: #F59E0B;")
        self._title.setText("Something went wrong")
        self._details.setText(message.replace("\n", "<br>"))
        self._undo.setVisible(False)
        self._open.setVisible(False)
