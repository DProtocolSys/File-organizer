"""Tests for the undo history."""

import json
from pathlib import Path

import pytest

from file_organizer import NothingToUndo, Resolution, organize, undo_last_session
from file_organizer.history import HISTORY_DIRNAME, has_history, load_sessions


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def snapshot(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_undo_restores_everything_and_removes_empty_folders(tmp_path: Path):
    write(tmp_path / "a.jpg", "a")
    write(tmp_path / "b.pdf", "b")
    before = snapshot(tmp_path)

    outcome = organize(tmp_path)
    assert outcome.count == 2
    assert has_history(tmp_path)

    report = undo_last_session(tmp_path)

    assert report.restored == 2 and report.complete
    assert snapshot(tmp_path) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.jpg", "b.pdf"]
    assert not has_history(tmp_path)


def test_undo_of_a_replacement_brings_the_old_file_back(tmp_path: Path):
    write(tmp_path / "photo.jpg", "new")
    write(tmp_path / "Images" / "photo.jpg", "old")
    before = snapshot(tmp_path)

    organize(tmp_path, on_conflict=Resolution.REPLACE)
    assert (tmp_path / "Images" / "photo.jpg").read_text(encoding="utf-8") == "new"

    report = undo_last_session(tmp_path)

    assert report.complete
    assert snapshot(tmp_path) == before


def test_undo_only_reverts_the_last_run(tmp_path: Path):
    write(tmp_path / "a.jpg")
    organize(tmp_path)
    write(tmp_path / "b.jpg")
    organize(tmp_path)

    undo_last_session(tmp_path)

    assert (tmp_path / "b.jpg").exists()
    assert (tmp_path / "Images" / "a.jpg").exists()
    assert len(load_sessions(tmp_path)) == 1


def test_undo_skips_files_the_user_moved_since(tmp_path: Path):
    write(tmp_path / "a.jpg", "a")
    write(tmp_path / "b.jpg", "b")
    organize(tmp_path)
    (tmp_path / "Images" / "a.jpg").unlink()  # the user deleted it meanwhile

    report = undo_last_session(tmp_path)

    assert report.restored == 1
    assert not report.complete
    assert [r.destination.name for r, _ in report.skipped] == ["a.jpg"]
    assert (tmp_path / "b.jpg").exists()
    assert has_history(tmp_path)  # still there so the undo can be retried


def test_undo_never_overwrites_a_new_file_at_the_original_place(tmp_path: Path):
    write(tmp_path / "a.jpg", "old")
    organize(tmp_path)
    write(tmp_path / "a.jpg", "brand new")

    report = undo_last_session(tmp_path)

    assert not report.complete
    assert (tmp_path / "a.jpg").read_text(encoding="utf-8") == "brand new"
    assert (tmp_path / "Images" / "a.jpg").read_text(encoding="utf-8") == "old"


def test_nothing_to_undo(tmp_path: Path):
    with pytest.raises(NothingToUndo):
        undo_last_session(tmp_path)


def test_history_survives_renaming_the_folder(tmp_path: Path):
    folder = tmp_path / "before"
    write(folder / "a.jpg")
    organize(folder)
    renamed = folder.rename(tmp_path / "after")

    report = undo_last_session(renamed)

    assert report.complete
    assert (renamed / "a.jpg").exists()


def test_corrupt_history_is_set_aside_not_fatal(tmp_path: Path):
    write(tmp_path / "a.jpg")
    organize(tmp_path)
    (tmp_path / HISTORY_DIRNAME / "history.json").write_text("{not json", encoding="utf-8")

    assert load_sessions(tmp_path) == []
    assert (tmp_path / HISTORY_DIRNAME / "history.json.corrupt").exists()


def test_history_file_is_valid_json_with_relative_paths(tmp_path: Path):
    write(tmp_path / "a.jpg")
    organize(tmp_path)

    data = json.loads((tmp_path / HISTORY_DIRNAME / "history.json").read_text(encoding="utf-8"))

    record = data["sessions"][0]["records"][0]
    assert record["source"] == "a.jpg"
    assert record["destination"] == "Images/a.jpg"


def test_history_folder_is_never_organized(tmp_path: Path):
    write(tmp_path / "a.jpg")
    organize(tmp_path)
    write(tmp_path / "b.jpg")

    outcome = organize(tmp_path)

    assert outcome.count == 1  # only b.jpg, nothing from .file_organizer


def test_empty_run_records_nothing(tmp_path: Path):
    outcome = organize(tmp_path)

    assert outcome.count == 0 and outcome.session is None
    assert not (tmp_path / HISTORY_DIRNAME).exists()
