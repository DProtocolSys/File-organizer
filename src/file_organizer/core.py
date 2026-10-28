"""Planning and execution engine.

The engine works in three separate steps so that nothing is ever moved
without the user's knowledge:

1. :func:`plan_organization` inspects a folder and returns a list of
   :class:`PlannedMove` objects. It never modifies anything. Moves that would
   collide with an existing file are flagged with a :class:`ConflictKind`.
2. :func:`resolve_conflicts` turns every flagged move into a concrete decision
   (skip, keep both, replace) using a policy or a callback, e.g. a dialog.
3. :func:`execute_plan` validates the whole plan, applies it, and rolls
   everything back if any step fails or is cancelled.
"""

from __future__ import annotations

import filecmp
import os
import shutil
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Union

from file_organizer.categories import OTHER_CATEGORY, get_category

__all__ = [
    "ConflictKind",
    "ExecutionResult",
    "MoveRecord",
    "OperationCancelled",
    "PlannedMove",
    "Resolution",
    "UnsafeFolderError",
    "can_replace",
    "execute_plan",
    "files_identical",
    "is_system_folder",
    "plan_organization",
    "resolve_conflicts",
    "unique_destination",
]


# --------------------------------------------------------------------------- #
# Errors and enums
# --------------------------------------------------------------------------- #
class OperationCancelled(Exception):
    """Raised when the user cancels an operation (everything is rolled back)."""


class UnsafeFolderError(ValueError):
    """Raised when asked to organize a system folder."""


class ConflictKind(str, Enum):
    """Why a planned move cannot be applied as-is."""

    #: A file or folder already exists at the destination.
    EXISTS = "exists"
    #: Another file of the same batch would land on the same name
    #: (names are compared case-insensitively).
    NAME_CLASH = "name_clash"


class Resolution(str, Enum):
    """What to do with a conflicting move."""

    SKIP = "skip"
    KEEP_BOTH = "keep_both"
    REPLACE = "replace"


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlannedMove:
    """A move that has been planned but not executed."""

    source: Path
    destination: Path
    category: str
    conflict: ConflictKind | None = None
    #: For ``EXISTS`` conflicts: the file that is actually in the way. It can
    #: differ from ``destination`` by letter case only.
    existing: Path | None = None
    #: Set by :func:`resolve_conflicts` when the user chose to replace.
    replace_existing: bool = False
    size: int = 0


@dataclass(frozen=True)
class MoveRecord:
    """A move that was really performed (enough information to undo it)."""

    source: Path
    destination: Path
    #: Path of a file that was replaced, and where its backup now lives.
    replaced: Path | None = None
    backup: Path | None = None


@dataclass
class ExecutionResult:
    """Outcome of a successful :func:`execute_plan`."""

    records: list[MoveRecord] = field(default_factory=list)
    created_dirs: list[Path] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.records)


Resolver = Union[Resolution, Callable[[PlannedMove], "Resolution | None"]]
ProgressCallback = Callable[[int, int, PlannedMove], None]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _key(path: str | os.PathLike[str]) -> str:
    """Normalized, case-insensitive identity of a path.

    Uses ``abspath`` (pure string work) rather than ``Path.resolve`` which
    performs filesystem calls: this keeps validation fast on large plans.
    Case is always folded so that plans behave the same on every OS (a plan
    made on Linux stays valid if the folder later lives on Windows or macOS).
    """
    return os.path.normcase(os.path.abspath(path)).casefold()


_POSIX_PROTECTED = frozenset(
    {"/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/proc",
     "/root", "/run", "/sbin", "/sys", "/usr", "/var", "/System", "/Library"}
)
_WINDOWS_PROTECTED = frozenset(
    {"windows", "program files", "program files (x86)", "programdata"}
)


def is_system_folder(folder: str | Path) -> bool:
    """Return True for drive roots and well-known operating-system folders."""
    path = Path(folder).expanduser().resolve()
    if path == Path(path.anchor):
        return True
    if os.name == "nt":
        parts = path.parts
        return len(parts) >= 2 and parts[1].lower() in _WINDOWS_PROTECTED
    return str(path) in _POSIX_PROTECTED


def files_identical(first: str | Path, second: str | Path) -> bool:
    """Return True if both files have exactly the same content."""
    try:
        return filecmp.cmp(first, second, shallow=False)
    except OSError:
        return False


def can_replace(move: PlannedMove) -> bool:
    """Return True if ``move`` may be resolved with :attr:`Resolution.REPLACE`.

    Only an existing regular file can be replaced; folders and name clashes
    inside the same batch cannot.
    """
    return (
        move.conflict is ConflictKind.EXISTS
        and move.existing is not None
        and move.existing.is_file()
        and not move.existing.is_symlink()
    )


def unique_destination(
    destination: Path, taken: Iterable[str] | None = None
) -> Path:
    """Return ``destination`` or ``name (1).ext``, ``name (2).ext``... that is free.

    A path is free when nothing exists there and its key is not in ``taken``
    (keys produced by the engine for other planned destinations).
    """
    taken_keys = set(taken or ())
    if not os.path.lexists(destination) and _key(destination) not in taken_keys:
        return destination

    stem, suffix = os.path.splitext(destination.name)
    counter = 1
    while True:
        candidate = destination.with_name(f"{stem} ({counter}){suffix}")
        if not os.path.lexists(candidate) and _key(candidate) not in taken_keys:
            return candidate
        counter += 1


# --------------------------------------------------------------------------- #
# Step 1: planning
# --------------------------------------------------------------------------- #
def plan_organization(
    folder: str | Path,
    *,
    include_hidden: bool = False,
    include_unknown: bool = False,
) -> list[PlannedMove]:
    """Prepare the sorting of the files located directly inside ``folder``.

    Nothing is modified and subfolders are not traversed. Symbolic links and
    (by default) hidden files are ignored. With ``include_unknown`` files with
    an unrecognized extension go to an ``Other`` folder instead of being left
    alone.

    Raises:
        FileNotFoundError: the folder does not exist.
        NotADirectoryError: the path is not a folder, or a file is already
            using the name of a category folder.
        UnsafeFolderError: the folder is a drive root or a system folder.
    """
    root = Path(folder).expanduser()

    if not root.exists():
        raise FileNotFoundError(f"Directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")
    if is_system_folder(root):
        raise UnsafeFolderError(
            f"Refusing to organize a system folder: {root.resolve()}"
        )

    # One directory listing per destination folder instead of one filesystem
    # query per file: this is what keeps planning fast on large folders.
    existing_cache: dict[str, dict[str, Path]] = {}

    def existing_names(category: str) -> dict[str, Path]:
        if category not in existing_cache:
            names: dict[str, Path] = {}
            try:
                with os.scandir(root / category) as entries:
                    for entry in entries:
                        names[entry.name.casefold()] = Path(entry.path)
            except FileNotFoundError:
                pass
            except NotADirectoryError:
                raise NotADirectoryError(
                    f"Cannot create the folder '{category}' in {root}: "
                    f"a file with that name already exists."
                ) from None
            existing_cache[category] = names
        return existing_cache[category]

    with os.scandir(root) as scan:
        entries = sorted(scan, key=lambda entry: entry.name.lower())

    claimed: set[tuple[str, str]] = set()
    moves: list[PlannedMove] = []

    for entry in entries:
        if not include_hidden and entry.name.startswith("."):
            continue
        try:
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                continue
            size = entry.stat(follow_symlinks=False).st_size
        except OSError:
            continue  # vanished or unreadable: leave it alone

        category = get_category(entry.name)
        if category is None:
            if not include_unknown:
                continue
            category = OTHER_CATEGORY

        name_key = entry.name.casefold()
        claim = (category, name_key)
        conflict: ConflictKind | None = None
        existing: Path | None = None

        if claim in claimed:
            conflict = ConflictKind.NAME_CLASH
        else:
            existing = existing_names(category).get(name_key)
            if existing is not None:
                conflict = ConflictKind.EXISTS
        claimed.add(claim)

        moves.append(
            PlannedMove(
                source=Path(entry.path),
                destination=root / category / entry.name,
                category=category,
                conflict=conflict,
                existing=existing,
                size=size,
            )
        )

    return moves


# --------------------------------------------------------------------------- #
# Step 2: conflict resolution
# --------------------------------------------------------------------------- #
def resolve_conflicts(
    moves: Iterable[PlannedMove], resolver: Resolver
) -> list[PlannedMove]:
    """Return a plan in which every conflict has been decided.

    ``resolver`` is either a :class:`Resolution` applied to every conflict, or
    a callable receiving the conflicting move and returning a
    :class:`Resolution`. A callable may return ``None`` to cancel everything,
    which raises :class:`OperationCancelled`.

    * ``SKIP``      removes the move from the plan.
    * ``KEEP_BOTH`` gives the incoming file a free name such as ``a (1).jpg``.
    * ``REPLACE``   marks the move so the existing file is backed up, then
      replaced. Not allowed where :func:`can_replace` is false.
    """
    moves = list(moves)
    # Names already claimed by the plan, so a renamed file never collides with
    # another file that is about to arrive.
    taken = {_key(move.destination) for move in moves}
    resolved: list[PlannedMove] = []

    for move in moves:
        if move.conflict is None:
            resolved.append(move)
            continue

        decision = resolver(move) if callable(resolver) else resolver
        if decision is None:
            raise OperationCancelled("Conflict resolution was cancelled.")
        decision = Resolution(decision)

        if decision is Resolution.SKIP:
            continue
        if decision is Resolution.KEEP_BOTH:
            destination = unique_destination(move.destination, taken)
            taken.add(_key(destination))
            resolved.append(
                replace(move, destination=destination, conflict=None,
                        existing=None)
            )
        else:
            if not can_replace(move):
                raise ValueError(
                    f"Cannot replace {move.destination}: only an existing "
                    f"file can be replaced."
                )
            resolved.append(replace(move, replace_existing=True))

    return resolved


# --------------------------------------------------------------------------- #
# Step 3: execution
# --------------------------------------------------------------------------- #
def _validate(moves: list[PlannedMove], backup_dir: Path | None) -> None:
    """Check the whole plan before touching anything."""
    sources = {_key(move.source) for move in moves}
    destinations: set[str] = set()

    for move in moves:
        if not move.source.is_file():
            raise FileNotFoundError(f"Source file not found: {move.source}")

        destination_key = _key(move.destination)
        if destination_key in destinations:
            raise ValueError(
                f"Multiple moves target the same destination: "
                f"{move.destination}"
            )
        destinations.add(destination_key)

        if move.replace_existing:
            if backup_dir is None:
                raise ValueError("A backup folder is required to replace files.")
            target = move.existing or move.destination
            if not target.is_file() or target.is_symlink():
                raise FileExistsError(
                    f"Refusing to replace something that is not a regular "
                    f"file: {target}"
                )
            if _key(target) in sources:
                raise FileExistsError(
                    f"The file to replace is itself being moved: {target}"
                )
        elif os.path.lexists(move.destination):
            raise FileExistsError(
                f"A file or directory already exists at the destination: "
                f"{move.destination}"
            )


def _ensure_parent(path: Path, created: list[Path]) -> None:
    """Create the parent folder of ``path`` and remember what was created."""
    missing: list[Path] = []
    folder = path.parent
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    created.extend(reversed(missing))


def _apply_move(
    move: PlannedMove,
    index: int,
    backup_dir: Path | None,
    created: list[Path],
) -> MoveRecord:
    _ensure_parent(move.destination, created)

    replaced: Path | None = None
    backup: Path | None = None

    if move.replace_existing:
        assert backup_dir is not None  # checked in _validate
        replaced = move.existing or move.destination
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{index:05d}_{replaced.name}"
        shutil.move(str(replaced), str(backup))
    elif os.path.lexists(move.destination):
        # Last-moment guard against a file that appeared since validation.
        raise FileExistsError(
            f"A file or directory already exists at the destination: "
            f"{move.destination}"
        )

    try:
        shutil.move(str(move.source), str(move.destination))
    except BaseException:
        if backup is not None and replaced is not None:
            shutil.move(str(backup), str(replaced))  # put the original back
        raise

    return MoveRecord(move.source, move.destination, replaced, backup)


def _rollback(
    done: list[MoveRecord], created: list[Path], original: BaseException
) -> None:
    """Undo ``done`` moves in reverse order; raise if something is left over."""
    errors: list[str] = []

    for record in reversed(done):
        try:
            record.source.parent.mkdir(parents=True, exist_ok=True)
            if record.source.exists():
                raise FileExistsError(
                    f"Cannot restore file because the source path "
                    f"already exists: {record.source}"
                )
            shutil.move(str(record.destination), str(record.source))
            if record.backup is not None and record.replaced is not None:
                shutil.move(str(record.backup), str(record.replaced))
        except Exception as error:  # keep going: restore as much as possible
            errors.append(f"{record.destination} -> {record.source}: {error}")

    for folder in reversed(created):
        try:
            folder.rmdir()  # only removes folders that are empty
        except OSError:
            pass

    if errors:
        details = "\n".join(errors)
        raise RuntimeError(
            "The operation failed and some files could not be restored:\n"
            f"{details}"
        ) from original


def execute_plan(
    moves: Iterable[PlannedMove],
    *,
    backup_dir: Path | None = None,
    on_progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ExecutionResult:
    """Apply a plan, all or nothing.

    The whole plan is validated first. If a move then fails, or
    ``should_cancel()`` returns True, every move already done is reverted
    (:class:`OperationCancelled` is raised for a cancellation).

    Existing files are never overwritten silently: a move onto an existing
    path is refused unless it was resolved with :attr:`Resolution.REPLACE`, in
    which case the old file is first moved into ``backup_dir``.
    """
    plan = list(moves)
    _validate(plan, backup_dir)

    total = len(plan)
    done: list[MoveRecord] = []
    created: list[Path] = []

    try:
        for index, move in enumerate(plan):
            if should_cancel is not None and should_cancel():
                raise OperationCancelled("Cancelled by the user.")
            done.append(_apply_move(move, index, backup_dir, created))
            if on_progress is not None:
                on_progress(index + 1, total, move)
    except BaseException as error:  # includes Ctrl+C: never leave a half-done job
        _rollback(done, created, error)
        raise

    return ExecutionResult(records=done, created_dirs=created)
