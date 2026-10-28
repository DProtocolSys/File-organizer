"""Tests for the command-line interface."""

from pathlib import Path

from file_organizer.cli import main


def write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_dry_run_changes_nothing(tmp_path: Path, capsys):
    write(tmp_path / "a.jpg")

    assert main(["organize", str(tmp_path), "--dry-run"]) == 0

    assert (tmp_path / "a.jpg").exists()
    assert "Images" in capsys.readouterr().out


def test_organize_then_undo(tmp_path: Path):
    write(tmp_path / "a.jpg")

    assert main(["organize", str(tmp_path), "--yes"]) == 0
    assert (tmp_path / "Images" / "a.jpg").exists()

    assert main(["undo", str(tmp_path)]) == 0
    assert (tmp_path / "a.jpg").exists()


def test_conflict_policy_skip(tmp_path: Path):
    write(tmp_path / "a.jpg", "new")
    write(tmp_path / "Images" / "a.jpg", "old")

    assert main(["organize", str(tmp_path), "-y", "--on-conflict", "skip"]) == 0

    assert (tmp_path / "a.jpg").read_text(encoding="utf-8") == "new"
    assert (tmp_path / "Images" / "a.jpg").read_text(encoding="utf-8") == "old"


def test_conflict_policy_replace(tmp_path: Path):
    write(tmp_path / "a.jpg", "new")
    write(tmp_path / "Images" / "a.jpg", "old")

    assert main(["organize", str(tmp_path), "-y", "--on-conflict", "replace"]) == 0

    assert (tmp_path / "Images" / "a.jpg").read_text(encoding="utf-8") == "new"
    assert main(["undo", str(tmp_path)]) == 0
    assert (tmp_path / "Images" / "a.jpg").read_text(encoding="utf-8") == "old"


def test_interactive_conflict_prompt(tmp_path: Path, monkeypatch):
    write(tmp_path / "a.jpg", "new")
    write(tmp_path / "Images" / "a.jpg", "old")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    answers = iter(["k"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert main(["organize", str(tmp_path), "-y"]) == 0

    assert (tmp_path / "Images" / "a (1).jpg").read_text(encoding="utf-8") == "new"


def test_abort_at_the_prompt_changes_nothing(tmp_path: Path, monkeypatch):
    write(tmp_path / "a.jpg", "new")
    write(tmp_path / "Images" / "a.jpg", "old")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "a")

    assert main(["organize", str(tmp_path), "-y"]) == 130

    assert (tmp_path / "a.jpg").exists()


def test_conflicts_without_terminal_require_a_policy(tmp_path: Path, monkeypatch, capsys):
    write(tmp_path / "a.jpg")
    write(tmp_path / "Images" / "a.jpg")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    assert main(["organize", str(tmp_path), "-y"]) == 1

    assert "--on-conflict" in capsys.readouterr().err
    assert (tmp_path / "a.jpg").exists()


def test_errors_are_reported_not_raised(tmp_path: Path, capsys):
    assert main(["organize", str(tmp_path / "missing"), "-y"]) == 1
    assert "error" in capsys.readouterr().err

    assert main(["undo", str(tmp_path)]) == 1


def test_categories_command(capsys):
    assert main(["categories"]) == 0
    assert "Images:" in capsys.readouterr().out
