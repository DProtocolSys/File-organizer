"""High-level operations combining the engine and the undo history."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from file_organizer.core import (
    ExecutionResult,
    PlannedMove,
    ProgressCallback,
    Resolution,
    Resolver,
    execute_plan,
    plan_organization,
    resolve_conflicts,
)
from file_organizer.history import (
    Session,
    backup_dir_for,
    new_session_id,
    record_session,
)

__all__ = ["ApplyOutcome", "apply_plan", "organize"]


@dataclass
class ApplyOutcome:
    """Result of applying a plan."""

    result: ExecutionResult
    session: Session | None
    #: Set when the files were moved but the undo history could not be saved.
    history_error: str | None = None

    @property
    def count(self) -> int:
        return self.result.count


def apply_plan(
    root: str | Path,
    moves: Iterable[PlannedMove],
    *,
    on_progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ApplyOutcome:
    """Execute an already-resolved plan and record it so it can be undone."""
    root = Path(root)
    session_id = new_session_id()
    result = execute_plan(
        moves,
        backup_dir=backup_dir_for(root, session_id),
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
    try:
        session = record_session(root, session_id, result)
    except OSError as error:
        return ApplyOutcome(result, None, history_error=str(error))
    return ApplyOutcome(result, session)


def organize(
    folder: str | Path,
    *,
    on_conflict: Resolver = Resolution.KEEP_BOTH,
    include_hidden: bool = False,
    include_unknown: bool = False,
    on_progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ApplyOutcome:
    """Plan, resolve conflicts, and execute in one call.

    ``on_conflict`` is a :class:`Resolution` applied to every conflict or a
    callable asked for each conflicting move (see :func:`resolve_conflicts`).
    """
    plan = plan_organization(
        folder, include_hidden=include_hidden, include_unknown=include_unknown
    )
    plan = resolve_conflicts(plan, on_conflict)
    return apply_plan(
        folder, plan, on_progress=on_progress, should_cancel=should_cancel
    )
