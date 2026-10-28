"""File Organizer: sort the files of a folder into category subfolders."""

from file_organizer.categories import FILE_CATEGORIES, OTHER_CATEGORY, get_category
from file_organizer.core import (
    ConflictKind,
    ExecutionResult,
    MoveRecord,
    OperationCancelled,
    PlannedMove,
    Resolution,
    UnsafeFolderError,
    execute_plan,
    plan_organization,
    resolve_conflicts,
)
from file_organizer.history import NothingToUndo, undo_last_session
from file_organizer.service import apply_plan, organize

__version__ = "1.0.0"

__all__ = [
    "FILE_CATEGORIES",
    "OTHER_CATEGORY",
    "ConflictKind",
    "ExecutionResult",
    "MoveRecord",
    "NothingToUndo",
    "OperationCancelled",
    "PlannedMove",
    "Resolution",
    "UnsafeFolderError",
    "__version__",
    "apply_plan",
    "execute_plan",
    "get_category",
    "organize",
    "plan_organization",
    "resolve_conflicts",
    "undo_last_session",
]
