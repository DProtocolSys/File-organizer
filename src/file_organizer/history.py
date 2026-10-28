"""Persistent undo history.

Every successful run is recorded in ``<folder>/.file_organizer/history.json``.
Files replaced by the user's choice are kept in
``<folder>/.file_organizer/replaced/<session>/`` so that *nothing is ever
destroyed*: undoing a run puts every file, including replaced ones, back.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from file_organizer.core import ExecutionResult, MoveRecord

__all__ = [
    "HISTORY_DIRNAME",
    "NothingToUndo",
    "Session",
    "UndoReport",
    "backup_dir_for",
    "has_history",
    "load_sessions",
    "new_session_id",
    "record_session",
    "undo_last_session",
]

HISTORY_DIRNAME = ".file_organizer"
_HISTORY_FILE = "history.json"
_SCHEMA_VERSION = 1


class NothingToUndo(Exception):
    """Raised when the folder has no recorded run to undo."""


@dataclass
class Session:
    """One recorded organization run."""

    id: str
    timestamp: str
    records: list[MoveRecord] = field(default_factory=list)
    created_dirs: list[Path] = field(default_factory=list)


@dataclass
class UndoReport:
    """What :func:`undo_last_session` managed to do."""

    restored: int = 0
    #: ``(record, reason)`` for every file that could not be put back.
    skipped: list[tuple[MoveRecord, str]] = field(default_factory=list)
    #: Backups that could not be put back (they are kept on disk).
    warnings: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.skipped and not self.warnings


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def _history_dir(root: Path) -> Path:
    return Path(root) / HISTORY_DIRNAME


def _history_file(root: Path) -> Path:
    return _history_dir(root) / _HISTORY_FILE


def new_session_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def backup_dir_for(root: Path, session_id: str) -> Path:
    """Folder where files replaced during ``session_id`` are kept."""
    return _history_dir(root) / "replaced" / session_id


# --------------------------------------------------------------------------- #
# (De)serialization: paths are stored relative to the organized folder so the
# folder can be renamed or moved without breaking its history.
# --------------------------------------------------------------------------- #
def _rel(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    return Path(os.path.relpath(path, root)).as_posix()


def _abs(root: Path, value: str | None) -> Path | None:
    return None if value is None else Path(root) / value


def _session_to_json(root: Path, session: Session) -> dict:
    return {
        "id": session.id,
        "timestamp": session.timestamp,
        "created_dirs": [_rel(root, d) for d in session.created_dirs],
        "records": [
            {
                "source": _rel(root, r.source),
                "destination": _rel(root, r.destination),
                "replaced": _rel(root, r.replaced),
                "backup": _rel(root, r.backup),
            }
            for r in session.records
        ],
    }


def _session_from_json(root: Path, data: dict) -> Session:
    return Session(
        id=data["id"],
        timestamp=data["timestamp"],
        created_dirs=[_abs(root, d) for d in data.get("created_dirs", [])],
        records=[
            MoveRecord(
                source=_abs(root, r["source"]),
                destination=_abs(root, r["destination"]),
                replaced=_abs(root, r.get("replaced")),
                backup=_abs(root, r.get("backup")),
            )
            for r in data["records"]
        ],
    )


def load_sessions(root: str | Path) -> list[Session]:
    """Return the recorded sessions, oldest first (empty if none)."""
    root = Path(root)
    path = _history_file(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [_session_from_json(root, item) for item in data["sessions"]]
    except FileNotFoundError:
        return []
    except (ValueError, KeyError, TypeError):
        # Damaged file: keep it for inspection and start from a clean slate.
        try:
            path.replace(path.with_suffix(".json.corrupt"))
        except OSError:
            pass
        return []


def has_history(root: str | Path) -> bool:
    return bool(load_sessions(root))


def _save_sessions(root: Path, sessions: list[Session]) -> None:
    folder = _history_dir(root)
    path = _history_file(root)

    if not sessions:
        path.unlink(missing_ok=True)
        for leftover in (folder / "replaced", folder):
            try:
                leftover.rmdir()
            except OSError:
                pass
        return

    folder.mkdir(exist_ok=True)
    payload = {
        "version": _SCHEMA_VERSION,
        "sessions": [_session_to_json(root, s) for s in sessions],
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, path)  # atomic: never leaves a half-written file


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def record_session(
    root: str | Path, session_id: str, result: ExecutionResult
) -> Session | None:
    """Append a finished run to the history. Returns None for an empty run."""
    if not result.records:
        return None
    root = Path(root)
    session = Session(
        id=session_id,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        records=list(result.records),
        created_dirs=list(result.created_dirs),
    )
    sessions = load_sessions(root)
    sessions.append(session)
    _save_sessions(root, sessions)
    return session


def undo_last_session(root: str | Path) -> UndoReport:
    """Put back every file moved by the most recent run.

    Files that were replaced are restored from their backup. A file that was
    moved or renamed by the user since is left alone and reported; it stays in
    the history so the undo can be retried.

    Raises:
        NothingToUndo: the folder has no recorded run.
    """
    root = Path(root)
    sessions = load_sessions(root)
    if not sessions:
        raise NothingToUndo(f"Nothing to undo in {root}")

    session = sessions[-1]
    report = UndoReport()
    remaining: list[MoveRecord] = []

    for record in reversed(session.records):
        if not os.path.lexists(record.destination):
            report.skipped.append((record, "the file is no longer where it was put"))
            remaining.append(record)
            continue
        if os.path.lexists(record.source):
            report.skipped.append(
                (record, "something else now uses the original location")
            )
            remaining.append(record)
            continue

        try:
            record.source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(record.destination), str(record.source))
        except OSError as error:
            report.skipped.append((record, str(error)))
            remaining.append(record)
            continue
        report.restored += 1

        if record.backup is not None and record.replaced is not None:
            if os.path.lexists(record.replaced) or not record.backup.exists():
                report.warnings.append(
                    f"The replaced file could not be put back at "
                    f"{record.replaced}; its backup is kept in {record.backup}"
                )
            else:
                try:
                    shutil.move(str(record.backup), str(record.replaced))
                except OSError as error:
                    report.warnings.append(
                        f"{record.replaced}: {error} (backup kept in "
                        f"{record.backup})"
                    )

    # Tidy up what the run created, but only when it is empty.
    for folder in reversed(session.created_dirs):
        try:
            folder.rmdir()
        except OSError:
            pass
    try:
        backup_dir_for(root, session.id).rmdir()
    except OSError:
        pass

    if remaining:
        session.records = list(reversed(remaining))
        sessions[-1] = session
    else:
        sessions.pop()
    _save_sessions(root, sessions)
    return report
