"""Main window and application entry point."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QRectF, QSettings, QUrl, Qt, Slot
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QStackedWidget,
)

from file_organizer import __version__, icon_design as design
from file_organizer.core import (
    OperationCancelled, PlannedMove, Resolution, can_replace,
    plan_organization, resolve_conflicts,
)
from file_organizer.gui.dialogs import ConflictDialog
from file_organizer.gui.pages import (
    ProgressPage, ResultPage, ReviewPage, WelcomePage,
)
from file_organizer.gui.theme import apply_theme
from file_organizer.gui.workers import Worker
from file_organizer.history import has_history, undo_last_session
from file_organizer.service import ApplyOutcome, apply_plan

WELCOME, REVIEW, PROGRESS, RESULT = range(4)


def _app_icon() -> QIcon:
    """Draw the icon from the shared design (see ``icon_design.py``)."""
    scale = 128 / design.GRID
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    def rounded(x, y, w, h, radius, color) -> None:
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(
            QRectF(x * scale, y * scale, w * scale, h * scale),
            radius * scale, radius * scale)

    rounded(*design.BACKGROUND, design.BACKGROUND_COLOR)
    for shape in design.SHAPES:
        rounded(*shape)
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("File Organizer")
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(820, 560)

        self._settings = QSettings("FileOrganizer", "FileOrganizer")
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(980, 660)

        self._folder: str | None = None
        self._workers: set[Worker] = set()
        self._active: Worker | None = None
        self._load_id = 0

        self.welcome = WelcomePage(self._settings)
        self.review = ReviewPage()
        self.progress = ProgressPage()
        self.result = ResultPage()

        self._stack = QStackedWidget()
        for page in (self.welcome, self.review, self.progress, self.result):
            self._stack.addWidget(page)
        self.setCentralWidget(self._stack)

        self.welcome.folder_chosen.connect(self.open_folder)
        self.review.back_requested.connect(self._go_welcome)
        self.review.reload_requested.connect(self._scan)
        self.review.organize_requested.connect(self._organize)
        self.review.undo_requested.connect(self._undo)
        self.progress.cancel_requested.connect(self._cancel_active)
        self.result.open_folder_requested.connect(self._open_in_explorer)
        self.result.undo_requested.connect(self._undo)
        self.result.again_requested.connect(self._go_welcome)

    # -- thread helper ---------------------------------------------------------
    def _run(self, task, on_success, on_failure, on_progress=None) -> Worker:
        worker = Worker(task)  # no Qt parent: Python owns it (see _on_worker_finished)
        self._workers.add(worker)
        # Queued connections guarantee the callbacks run in the GUI thread,
        # never in the worker thread (widgets must only be touched from the
        # GUI thread).
        queued = Qt.ConnectionType.QueuedConnection
        worker.succeeded.connect(on_success, queued)
        worker.failed.connect(on_failure, queued)
        if on_progress:
            worker.progress.connect(on_progress, queued)
        worker.finished.connect(self._on_worker_finished, queued)
        worker.start()
        return worker

    @Slot()
    def _on_worker_finished(self) -> None:
        """Forget a worker once its thread has really stopped."""
        worker = self.sender()
        if isinstance(worker, Worker):
            worker.wait()  # `finished` fires just before the thread fully exits
            self._workers.discard(worker)

    def _cancel_active(self) -> None:
        if self._active is not None:
            self._active.cancel()

    # -- navigation ------------------------------------------------------------
    def _go_welcome(self) -> None:
        self.welcome.refresh_recent()
        self._stack.setCurrentIndex(WELCOME)

    def open_folder(self, folder: str) -> None:
        self._folder = folder
        self.welcome.remember(folder)
        self.review.set_folder(folder, has_history(folder))
        self._stack.setCurrentIndex(REVIEW)
        self._scan()

    def _scan(self) -> None:
        if self._folder is None:
            return
        folder = self._folder
        include_unknown = self.review.unknown_box.isChecked()
        include_hidden = self.review.hidden_box.isChecked()
        self._load_id += 1
        token = self._load_id
        self.review.show_scanning()

        def task(_progress, _cancelled):
            return plan_organization(
                folder, include_hidden=include_hidden, include_unknown=include_unknown)

        def done(moves):
            if token == self._load_id:  # ignore stale scans
                self.review.show_plan(moves)

        def failed(error):
            if token == self._load_id:
                self.review.show_error(str(error))

        self._run(task, done, failed)

    # -- conflicts -------------------------------------------------------------
    def _make_resolver(self, total: int):
        state: dict = {"position": 0, "sticky": None}

        def resolver(move: PlannedMove) -> Resolution | None:
            state["position"] += 1
            sticky = state["sticky"]
            if sticky is not None:
                if sticky is Resolution.REPLACE and not can_replace(move):
                    return Resolution.KEEP_BOTH
                return sticky
            dialog = ConflictDialog(move, state["position"], total, self)
            if dialog.exec() != ConflictDialog.DialogCode.Accepted:
                return None
            if dialog.apply_to_all:
                state["sticky"] = dialog.resolution
            return dialog.resolution

        return resolver

    # -- organize --------------------------------------------------------------
    def _organize(self) -> None:
        moves = self.review.selected_moves()
        if not moves or self._folder is None:
            return
        folder = self._folder
        conflicts = sum(1 for move in moves if move.conflict)

        try:
            resolved = resolve_conflicts(moves, self._make_resolver(conflicts))
        except OperationCancelled:
            return
        except ValueError as error:
            QMessageBox.warning(self, "File Organizer", str(error))
            return
        if not resolved:
            QMessageBox.information(self, "File Organizer", "Nothing left to move.")
            return

        skipped = len(moves) - len(resolved)
        counts = Counter(move.category for move in resolved)
        self.progress.start("Organizing…")
        self._stack.setCurrentIndex(PROGRESS)

        def task(report, cancelled):
            return apply_plan(
                folder, resolved,
                on_progress=lambda done, total, move: report(done, total, move.source.name),
                should_cancel=cancelled)

        def done(outcome: ApplyOutcome) -> None:
            self._active = None
            notes = []
            if skipped:
                notes.append(f"{skipped} file{'s' if skipped != 1 else ''} skipped.")
            if outcome.history_error:
                notes.append("The undo history could not be saved: " + outcome.history_error)
            self.result.show_success(
                dict(counts), can_undo=outcome.session is not None, note=" ".join(notes))
            self._stack.setCurrentIndex(RESULT)

        def failed(error: BaseException) -> None:
            self._active = None
            if isinstance(error, OperationCancelled):
                self._scan()
                self._stack.setCurrentIndex(REVIEW)
                QMessageBox.information(
                    self, "File Organizer", "Cancelled. Every file was put back.")
                return
            self.result.show_error(
                f"{error}\n\nThe files that were already moved have been put back.")
            self._stack.setCurrentIndex(RESULT)

        self._active = self._run(task, done, failed, self.progress.update_progress)

    # -- undo ------------------------------------------------------------------
    def _undo(self) -> None:
        if self._folder is None:
            return
        folder = self._folder
        answer = QMessageBox.question(
            self, "Undo last run",
            f"Put the files of the last run back where they were?\n\n{folder}")
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.progress.start("Restoring files…", cancellable=False)
        self._stack.setCurrentIndex(PROGRESS)

        def done(report) -> None:
            lines = [f"{report.restored} file(s) restored."]
            lines += [f"• {r.destination.name}: {why}" for r, why in report.skipped]
            lines += [f"• {w}" for w in report.warnings]
            box = QMessageBox.information if report.complete else QMessageBox.warning
            box(self, "Undo", "\n".join(lines))
            self.open_folder(folder)

        def failed(error: BaseException) -> None:
            QMessageBox.warning(self, "Undo", str(error))
            self.open_folder(folder)

        self._run(lambda _p, _c: undo_last_session(folder), done, failed)

    def _open_in_explorer(self) -> None:
        if self._folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._folder))

    def closeEvent(self, event) -> None:
        self._settings.setValue("geometry", self.saveGeometry())
        for worker in list(self._workers):
            worker.cancel()
            worker.wait(5000)  # a cancelled run rolls itself back first
        super().closeEvent(event)


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("File Organizer")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    apply_theme(app)

    window = MainWindow()
    window.show()
    if len(argv) > 1 and Path(argv[1]).is_dir():
        window.open_folder(str(Path(argv[1]).resolve()))
    return app.exec()
