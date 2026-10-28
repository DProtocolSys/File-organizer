"""Smoke and behaviour tests for the graphical interface."""

import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLabel  # noqa: E402

import file_organizer.gui.app as gui_app  # noqa: E402
from file_organizer.core import ConflictKind, PlannedMove, Resolution, plan_organization  # noqa: E402
from file_organizer.gui.dialogs import ConflictDialog  # noqa: E402
from file_organizer.gui.models import PlanModel  # noqa: E402


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def qapp(tmp_path_factory):
    # Keep the tests away from the real user settings.
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope,
        str(tmp_path_factory.mktemp("settings")),
    )
    return QApplication.instance() or QApplication([])


def wait_until(app, condition, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the condition")


@pytest.fixture(autouse=True)
def messages(monkeypatch):
    """Replace modal message boxes (they would block forever in tests)."""
    shown: list[tuple[str, str]] = []

    def recorder(kind, answer=None):
        def show(parent, title, text, *args, **kwargs):
            shown.append((kind, text))
            return answer
        return show

    box = gui_app.QMessageBox
    monkeypatch.setattr(box, "information", recorder("information"))
    monkeypatch.setattr(box, "warning", recorder("warning"))
    monkeypatch.setattr(box, "critical", recorder("critical"))
    monkeypatch.setattr(box, "question", recorder("question", box.StandardButton.Yes))
    return shown


@pytest.fixture
def window(qapp):
    win = gui_app.MainWindow()
    win.show()
    yield win
    win.close()
    wait_until(qapp, lambda: not win._workers)  # let every thread finish


class FakeDialog:
    """Stands in for ConflictDialog and answers automatically."""

    DialogCode = QDialog.DialogCode
    answers: list = []
    asked: list = []

    def __init__(self, move, position, total, parent=None):
        self.move = move
        self.resolution = None
        self.apply_to_all = False

    def exec(self):
        FakeDialog.asked.append(self.move.source.name)
        answer = FakeDialog.answers.pop(0)
        if answer is None:
            return QDialog.DialogCode.Rejected
        self.resolution, self.apply_to_all = answer
        return QDialog.DialogCode.Accepted


@pytest.fixture
def fake_dialog(monkeypatch):
    FakeDialog.answers, FakeDialog.asked = [], []
    monkeypatch.setattr(gui_app, "ConflictDialog", FakeDialog)
    return FakeDialog


# --------------------------------------------------------------------------- #
def test_model_checking_and_category_selection(qapp, tmp_path: Path):
    for name in ("a.jpg", "b.jpg", "c.pdf"):
        write(tmp_path / name)
    model = PlanModel()
    model.set_moves(plan_organization(tmp_path))

    assert len(model.selected_moves()) == 3

    model.set_category_checked("Images", False)
    assert [m.source.name for m in model.selected_moves()] == ["c.pdf"]

    index = model.index(2, 0)
    assert model.setData(index, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    assert model.selected_moves() == []

    model.set_all_checked(True)
    assert len(model.selected_moves()) == 3


def test_conflict_dialog_returns_the_clicked_choice(qapp, tmp_path: Path):
    write(tmp_path / "a.jpg", "new")
    write(tmp_path / "Images" / "a.jpg", "old")
    (move,) = plan_organization(tmp_path)

    dialog = ConflictDialog(move, 1, 3)
    dialog._all.setChecked(True)
    dialog._choose(Resolution.REPLACE)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.resolution is Resolution.REPLACE
    assert dialog.apply_to_all


def test_conflict_dialog_hides_replace_when_impossible(qapp, tmp_path: Path):
    write(tmp_path / "a.jpg")
    (tmp_path / "Images" / "a.jpg").mkdir(parents=True)  # a folder in the way
    (move,) = plan_organization(tmp_path)

    dialog = ConflictDialog(move, 1, 1)

    assert not dialog._replaceable
    titles = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Replace" not in titles
    assert "Keep both" in titles and "Skip" in titles


def test_full_flow_with_conflict_choices(qapp, window, fake_dialog, tmp_path: Path):
    write(tmp_path / "a.jpg", "A")
    write(tmp_path / "b.jpg", "B")
    write(tmp_path / "c.pdf", "C")
    write(tmp_path / "Images" / "a.jpg", "old A")
    write(tmp_path / "Images" / "b.jpg", "old B")

    window.open_folder(str(tmp_path))
    wait_until(qapp, lambda: window.review.model.rowCount() == 3)

    # a.jpg -> keep both, b.jpg -> skip
    fake_dialog.answers = [(Resolution.KEEP_BOTH, False), (Resolution.SKIP, False)]
    window._organize()
    wait_until(qapp, lambda: window._stack.currentIndex() == gui_app.RESULT)

    assert fake_dialog.asked == ["a.jpg", "b.jpg"]
    images = tmp_path / "Images"
    assert (images / "a.jpg").read_text(encoding="utf-8") == "old A"
    assert (images / "a (1).jpg").read_text(encoding="utf-8") == "A"
    assert (tmp_path / "b.jpg").exists()  # skipped
    assert (tmp_path / "Documents" / "c.pdf").exists()


def test_apply_to_all_asks_only_once(qapp, window, fake_dialog, messages, tmp_path: Path):
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        write(tmp_path / name, name)
        write(tmp_path / "Images" / name, "old")

    window.open_folder(str(tmp_path))
    wait_until(qapp, lambda: window.review.model.rowCount() == 3)
    fake_dialog.answers = [(Resolution.SKIP, True)]
    window._organize()

    assert fake_dialog.asked == ["a.jpg"]  # the other two reuse the answer
    assert all((tmp_path / n).exists() for n in ("a.jpg", "b.jpg", "c.jpg"))
    assert any("Nothing left to move" in text for _, text in messages)


def test_cancelling_a_conflict_dialog_changes_nothing(qapp, window, fake_dialog, tmp_path: Path):
    write(tmp_path / "a.jpg")
    write(tmp_path / "b.pdf")
    write(tmp_path / "Images" / "a.jpg")

    window.open_folder(str(tmp_path))
    wait_until(qapp, lambda: window.review.model.rowCount() == 2)
    fake_dialog.answers = [None]
    window._organize()

    assert window._stack.currentIndex() == gui_app.REVIEW
    assert (tmp_path / "b.pdf").exists()
    assert not (tmp_path / "Documents").exists()


def test_unchecked_files_are_left_alone(qapp, window, tmp_path: Path):
    write(tmp_path / "a.jpg")
    write(tmp_path / "b.pdf")

    window.open_folder(str(tmp_path))
    wait_until(qapp, lambda: window.review.model.rowCount() == 2)
    window.review.model.set_category_checked("Documents", False)
    window._organize()
    wait_until(qapp, lambda: window._stack.currentIndex() == gui_app.RESULT)

    assert (tmp_path / "Images" / "a.jpg").exists()
    assert (tmp_path / "b.pdf").exists()


def test_undo_from_the_result_page(qapp, window, tmp_path: Path):
    write(tmp_path / "a.jpg")

    window.open_folder(str(tmp_path))
    wait_until(qapp, lambda: window.review.model.rowCount() == 1)
    window._organize()
    wait_until(qapp, lambda: window._stack.currentIndex() == gui_app.RESULT)
    assert (tmp_path / "Images" / "a.jpg").exists()

    window._undo()
    wait_until(qapp, lambda: (tmp_path / "a.jpg").exists())
    wait_until(qapp, lambda: window._stack.currentIndex() == gui_app.REVIEW)

    assert not (tmp_path / "Images").exists()


def test_empty_folder_shows_a_friendly_message(qapp, window, tmp_path: Path):
    window.open_folder(str(tmp_path))
    wait_until(qapp, lambda: window.review._stack.currentIndex() == 2)

    assert not window.review._go.isEnabled()


def test_system_folder_is_reported_in_the_window(qapp, window, tmp_path: Path):
    window.open_folder(tmp_path.anchor)
    wait_until(qapp, lambda: window.review._stack.currentIndex() == 2)

    assert "system folder" in window.review._empty.label.text()


def test_recent_folders_can_be_removed_and_cleared(qapp, window, tmp_path: Path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    welcome = window.welcome
    welcome.clear_recent()

    welcome.remember(str(first))
    welcome.remember(str(second))
    assert welcome.recent() == [str(second), str(first)]

    welcome.forget(str(second))
    assert welcome.recent() == [str(first)]

    welcome.clear_recent()
    assert welcome.recent() == []
    assert welcome._recent_box.count() == 0  # the section is gone from the screen


def test_clearing_recent_folders_does_not_touch_undo_history(qapp, window, tmp_path: Path):
    write(tmp_path / "a.jpg")
    window.open_folder(str(tmp_path))
    wait_until(qapp, lambda: window.review.model.rowCount() == 1)
    window._organize()
    wait_until(qapp, lambda: window._stack.currentIndex() == gui_app.RESULT)

    window.welcome.clear_recent()

    from file_organizer.history import has_history
    assert has_history(tmp_path)


def test_refreshing_recent_folders_leaves_no_stale_widgets(qapp, window, tmp_path: Path):
    """Old buttons must be detached at once, not painted until the next event."""
    from PySide6.QtWidgets import QPushButton

    welcome = window.welcome
    welcome.clear_recent()
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
        welcome.remember(str(tmp_path / name))  # three refreshes, no event loop between

    buttons = welcome.findChildren(QPushButton)
    # Clear + 3 x (folder button + remove button)
    assert len(buttons) == 7
