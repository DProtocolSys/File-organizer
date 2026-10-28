"""Tests for the planning and execution engine."""

import os
from pathlib import Path

import pytest

import file_organizer.core as core
from file_organizer import execute_plan, get_category, plan_organization
from file_organizer.core import (
    ConflictKind,
    OperationCancelled,
    PlannedMove,
    Resolution,
    UnsafeFolderError,
    can_replace,
    resolve_conflicts,
    unique_destination,
)


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def is_case_sensitive(folder: Path) -> bool:
    """True if the filesystem can hold 'a' and 'A' as two different files."""
    probe = write(folder / "CaseProbe")
    try:
        return not (folder / "caseprobe").exists()
    finally:
        probe.unlink()


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
def test_recognizes_extensions_without_case_sensitivity():
    assert get_category("photo.JPG") == "Images"
    assert get_category("report.XLSX") == "Spreadsheets"
    assert get_category("script.py") == "Code"


def test_unknown_extension_is_ignored(tmp_path: Path):
    unknown_file = write(tmp_path / "file.unknown", "content")

    assert plan_organization(tmp_path) == []
    assert unknown_file.exists()


def test_unknown_files_go_to_other_when_requested(tmp_path: Path):
    write(tmp_path / "file.unknown")

    plan = plan_organization(tmp_path, include_unknown=True)

    assert [(m.source.name, m.category) for m in plan] == [("file.unknown", "Other")]


def test_plan_does_not_move_files(tmp_path: Path):
    source = write(tmp_path / "photo.jpg", "image")

    plan = plan_organization(tmp_path)

    assert len(plan) == 1
    assert plan[0].destination == tmp_path / "Images" / "photo.jpg"
    assert plan[0].size == len("image")
    assert plan[0].conflict is None
    assert source.exists()
    assert not plan[0].destination.exists()


def test_subdirectories_are_not_processed_recursively(tmp_path: Path):
    nested_file = write(tmp_path / "My documents" / "photo.jpg", "image")

    assert plan_organization(tmp_path) == []
    assert nested_file.exists()


def test_hidden_files_are_ignored_unless_requested(tmp_path: Path):
    write(tmp_path / ".secret.jpg")

    assert plan_organization(tmp_path) == []
    assert len(plan_organization(tmp_path, include_hidden=True)) == 1


def test_symbolic_links_are_ignored(tmp_path: Path):
    target = write(tmp_path / "elsewhere" / "real.txt")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available")

    assert plan_organization(tmp_path) == []


def test_invalid_directory_raises_error(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        plan_organization(tmp_path / "nonexistent")

    ordinary_file = write(tmp_path / "document.txt", "test")
    with pytest.raises(NotADirectoryError):
        plan_organization(ordinary_file)


def test_system_folders_are_refused(tmp_path: Path):
    with pytest.raises(UnsafeFolderError):
        plan_organization(Path(tmp_path.anchor))


def test_file_using_a_category_name_is_reported(tmp_path: Path):
    write(tmp_path / "photo.jpg")
    write(tmp_path / "Images")  # a *file* called Images

    with pytest.raises(NotADirectoryError, match="Images"):
        plan_organization(tmp_path)


def test_plan_is_sorted_case_insensitively(tmp_path: Path):
    for name in ("b.jpg", "A.jpg", "c.jpg"):
        write(tmp_path / name)

    assert [m.source.name for m in plan_organization(tmp_path)] == [
        "A.jpg", "b.jpg", "c.jpg",
    ]


# --------------------------------------------------------------------------- #
# Conflict detection and resolution
# --------------------------------------------------------------------------- #
def test_existing_destination_is_flagged_as_conflict(tmp_path: Path):
    write(tmp_path / "photo.jpg", "new")
    existing = write(tmp_path / "Images" / "photo.jpg", "old")

    (move,) = plan_organization(tmp_path)

    assert move.conflict is ConflictKind.EXISTS
    assert move.existing == existing
    assert can_replace(move)


def test_names_differing_only_by_case_clash(tmp_path: Path):
    # Only possible on case-sensitive filesystems (Linux); on Windows and macOS
    # the second file would simply overwrite the first one.
    if not is_case_sensitive(tmp_path):
        pytest.skip("this filesystem cannot hold two names differing only by case")
    write(tmp_path / "Photo.jpg")
    write(tmp_path / "photo.JPG")

    first, second = plan_organization(tmp_path)

    assert first.conflict is None
    assert second.conflict is ConflictKind.NAME_CLASH
    assert not can_replace(second)


def test_existing_file_differing_only_by_case_is_a_conflict(tmp_path: Path):
    """Runs on every OS: an existing 'photo.jpg' blocks an incoming 'Photo.JPG'."""
    write(tmp_path / "Photo.JPG", "new")
    existing = write(tmp_path / "Images" / "photo.jpg", "old")

    (move,) = plan_organization(tmp_path)

    assert move.conflict is ConflictKind.EXISTS
    assert move.existing is not None
    assert move.existing.name == existing.name  # the file that is really there


def test_executing_an_unresolved_conflict_never_overwrites(tmp_path: Path):
    source = write(tmp_path / "photo.jpg", "original")
    destination = write(tmp_path / "Images" / "photo.jpg", "existing")

    with pytest.raises(FileExistsError):
        execute_plan(plan_organization(tmp_path))

    assert source.read_text(encoding="utf-8") == "original"
    assert destination.read_text(encoding="utf-8") == "existing"


def test_resolution_skip_leaves_file_in_place(tmp_path: Path):
    source = write(tmp_path / "photo.jpg", "new")
    write(tmp_path / "Images" / "photo.jpg", "old")

    plan = resolve_conflicts(plan_organization(tmp_path), Resolution.SKIP)

    assert plan == []
    assert source.exists()


def test_resolution_keep_both_renames_the_incoming_file(tmp_path: Path):
    write(tmp_path / "photo.jpg", "new")
    write(tmp_path / "Images" / "photo.jpg", "old")
    write(tmp_path / "Images" / "photo (1).jpg", "older")

    plan = resolve_conflicts(plan_organization(tmp_path), Resolution.KEEP_BOTH)
    execute_plan(plan)

    images = tmp_path / "Images"
    assert (images / "photo.jpg").read_text(encoding="utf-8") == "old"
    assert (images / "photo (1).jpg").read_text(encoding="utf-8") == "older"
    assert (images / "photo (2).jpg").read_text(encoding="utf-8") == "new"


def test_keep_both_never_collides_with_another_planned_file(tmp_path: Path):
    write(tmp_path / "photo.jpg", "a")
    write(tmp_path / "Images" / "photo.jpg", "old")
    write(tmp_path / "photo (1).jpg", "b")  # will itself land in Images/

    plan = resolve_conflicts(plan_organization(tmp_path), Resolution.KEEP_BOTH)
    execute_plan(plan)

    contents = sorted(p.read_text(encoding="utf-8") for p in (tmp_path / "Images").iterdir())
    assert contents == ["a", "b", "old"]


def test_resolution_replace_backs_up_the_old_file(tmp_path: Path):
    write(tmp_path / "photo.jpg", "new")
    write(tmp_path / "Images" / "photo.jpg", "old")
    backup = tmp_path / "backup"

    plan = resolve_conflicts(plan_organization(tmp_path), Resolution.REPLACE)
    result = execute_plan(plan, backup_dir=backup)

    assert (tmp_path / "Images" / "photo.jpg").read_text(encoding="utf-8") == "new"
    (record,) = result.records
    assert record.backup is not None
    assert record.backup.read_text(encoding="utf-8") == "old"


def test_replace_requires_a_backup_folder(tmp_path: Path):
    write(tmp_path / "photo.jpg", "new")
    write(tmp_path / "Images" / "photo.jpg", "old")
    plan = resolve_conflicts(plan_organization(tmp_path), Resolution.REPLACE)

    with pytest.raises(ValueError, match="backup"):
        execute_plan(plan)


def test_a_directory_cannot_be_replaced(tmp_path: Path):
    write(tmp_path / "photo.jpg")
    (tmp_path / "Images" / "photo.jpg").mkdir(parents=True)

    (move,) = plan_organization(tmp_path)

    assert move.conflict is ConflictKind.EXISTS
    assert not can_replace(move)
    with pytest.raises(ValueError, match="Cannot replace"):
        resolve_conflicts([move], Resolution.REPLACE)


def test_resolver_callback_decides_per_file(tmp_path: Path):
    write(tmp_path / "a.jpg", "a")
    write(tmp_path / "b.jpg", "b")
    write(tmp_path / "Images" / "a.jpg", "old a")
    write(tmp_path / "Images" / "b.jpg", "old b")

    decisions = {"a.jpg": Resolution.SKIP, "b.jpg": Resolution.KEEP_BOTH}
    plan = resolve_conflicts(
        plan_organization(tmp_path), lambda move: decisions[move.source.name]
    )

    assert [m.destination.name for m in plan] == ["b (1).jpg"]


def test_resolver_returning_none_cancels(tmp_path: Path):
    write(tmp_path / "a.jpg")
    write(tmp_path / "Images" / "a.jpg")

    with pytest.raises(OperationCancelled):
        resolve_conflicts(plan_organization(tmp_path), lambda move: None)


def test_unique_destination_returns_same_path_when_free(tmp_path: Path):
    path = tmp_path / "free.txt"
    assert unique_destination(path) == path


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def test_execution_moves_files_into_category(tmp_path: Path):
    source = write(tmp_path / "photo.jpg", "image")

    result = execute_plan(plan_organization(tmp_path))

    assert result.count == 1
    assert not source.exists()
    assert (tmp_path / "Images" / "photo.jpg").read_text(encoding="utf-8") == "image"


def test_progress_callback_reports_every_move(tmp_path: Path):
    for name in ("a.jpg", "b.png", "c.gif"):
        write(tmp_path / name)
    calls = []

    execute_plan(
        plan_organization(tmp_path),
        on_progress=lambda done, total, move: calls.append((done, total)),
    )

    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_cancellation_rolls_everything_back(tmp_path: Path):
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        write(tmp_path / name, name)
    plan = plan_organization(tmp_path)
    moved = 0

    def on_progress(done, total, move):
        nonlocal moved
        moved = done

    with pytest.raises(OperationCancelled):
        execute_plan(plan, on_progress=on_progress, should_cancel=lambda: moved >= 2)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.jpg", "b.jpg", "c.jpg"]


def test_failed_move_rolls_back_previous_moves(tmp_path: Path, monkeypatch):
    first_source = write(tmp_path / "first.jpg", "first")
    second_source = write(tmp_path / "second.jpg", "second")
    plan = plan_organization(tmp_path)

    original_move = core.shutil.move
    call_count = 0

    def failing_move(source, destination):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("Simulated move failure")
        return original_move(source, destination)

    monkeypatch.setattr(core.shutil, "move", failing_move)

    with pytest.raises(OSError, match="Simulated move failure"):
        execute_plan(plan)

    assert first_source.read_text(encoding="utf-8") == "first"
    assert second_source.read_text(encoding="utf-8") == "second"
    # the folder created for the run is removed as well
    assert not (tmp_path / "Images").exists()


def test_failed_replace_restores_the_original_file(tmp_path: Path, monkeypatch):
    write(tmp_path / "photo.jpg", "new")
    existing = write(tmp_path / "Images" / "photo.jpg", "old")
    plan = resolve_conflicts(plan_organization(tmp_path), Resolution.REPLACE)

    original_move = core.shutil.move
    calls = []

    def failing_move(source, destination):
        calls.append(source)
        if len(calls) == 2:  # call 1 = backup, call 2 = the real move
            raise OSError("disk error")
        return original_move(source, destination)

    monkeypatch.setattr(core.shutil, "move", failing_move)

    with pytest.raises(OSError, match="disk error"):
        execute_plan(plan, backup_dir=tmp_path / "backup")

    assert existing.read_text(encoding="utf-8") == "old"
    assert (tmp_path / "photo.jpg").read_text(encoding="utf-8") == "new"


def test_rollback_failure_reports_files_that_could_not_be_restored(
    tmp_path: Path, monkeypatch
):
    first_source = write(tmp_path / "first.jpg", "first")
    second_source = write(tmp_path / "second.jpg", "second")
    plan = plan_organization(tmp_path)

    original_move = core.shutil.move
    call_count = 0

    def failing_move(source, destination):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("Simulated move failure")
        if call_count == 3:
            raise OSError("Simulated rollback failure")
        return original_move(source, destination)

    monkeypatch.setattr(core.shutil, "move", failing_move)

    with pytest.raises(RuntimeError, match="some files could not be restored") as info:
        execute_plan(plan)

    message = str(info.value)
    assert "first.jpg" in message
    assert "Simulated rollback failure" in message
    assert second_source.exists()
    assert not first_source.exists()
    assert (tmp_path / "Images" / "first.jpg").read_text(encoding="utf-8") == "first"


def test_missing_source_is_rejected_before_anything_moves(tmp_path: Path):
    real = write(tmp_path / "real.jpg")
    ghost = PlannedMove(tmp_path / "ghost.jpg", tmp_path / "Images" / "ghost.jpg", "Images")
    plan = plan_organization(tmp_path) + [ghost]

    with pytest.raises(FileNotFoundError):
        execute_plan(plan)

    assert real.exists()


# --- plan validation (hand-built plans) ------------------------------------ #
def _manual_plan(tmp_path: Path, first_dest: Path, second_dest: Path):
    first = write(tmp_path / "first.jpg", "first")
    second = write(tmp_path / "second.jpg", "second")
    return first, second, [
        PlannedMove(first, first_dest, "Images"),
        PlannedMove(second, second_dest, "Images"),
    ]


def test_duplicate_destinations_are_rejected_before_moving_files(tmp_path: Path):
    destination = tmp_path / "Images" / "photo.jpg"
    first, second, plan = _manual_plan(tmp_path, destination, destination)

    with pytest.raises(ValueError, match="Multiple moves target the same destination"):
        execute_plan(plan)

    assert first.exists() and second.exists()
    assert not destination.exists()


def test_equivalent_destination_paths_are_rejected(tmp_path: Path):
    destination = tmp_path / "Images" / "photo.jpg"
    equivalent = tmp_path / "Images" / ".." / "Images" / "photo.jpg"
    first, second, plan = _manual_plan(tmp_path, destination, equivalent)

    with pytest.raises(ValueError, match="Multiple moves target the same destination"):
        execute_plan(plan)

    assert first.read_text(encoding="utf-8") == "first"
    assert second.read_text(encoding="utf-8") == "second"


def test_destination_paths_with_different_case_are_rejected(tmp_path: Path):
    """Same behaviour on every OS, so a plan stays valid on any filesystem."""
    first, second, plan = _manual_plan(
        tmp_path, tmp_path / "Images" / "Photo.jpg", tmp_path / "Images" / "photo.jpg"
    )

    with pytest.raises(ValueError, match="Multiple moves target the same destination"):
        execute_plan(plan)

    assert first.exists() and second.exists()
    assert not (tmp_path / "Images").exists()


def test_destination_cannot_be_another_move_source(tmp_path: Path):
    first = write(tmp_path / "photo.jpg", "first")
    second = write(tmp_path / "other.jpg", "second")
    plan = [
        PlannedMove(first, tmp_path / "Images" / "photo.jpg", "Images"),
        PlannedMove(second, first, "Images"),
    ]

    with pytest.raises(FileExistsError):
        execute_plan(plan)

    assert first.read_text(encoding="utf-8") == "first"
    assert second.read_text(encoding="utf-8") == "second"
    assert not (tmp_path / "Images").exists()


# --------------------------------------------------------------------------- #
# Scale
# --------------------------------------------------------------------------- #
def test_handles_thousands_of_files(tmp_path: Path):
    for index in range(3000):
        write(tmp_path / f"file_{index}.{'jpg' if index % 2 else 'pdf'}")

    plan = plan_organization(tmp_path)
    result = execute_plan(plan)

    assert len(plan) == result.count == 3000
    assert len(os.listdir(tmp_path / "Images")) == 1500
    assert len(os.listdir(tmp_path / "Documents")) == 1500
