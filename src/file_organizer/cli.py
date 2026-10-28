"""Command-line interface: ``file-organizer-cli``."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Sequence

from file_organizer import __version__
from file_organizer.categories import FILE_CATEGORIES, OTHER_CATEGORY
from file_organizer.core import (
    ConflictKind,
    OperationCancelled,
    PlannedMove,
    Resolution,
    UnsafeFolderError,
    can_replace,
    files_identical,
    plan_organization,
    resolve_conflicts,
)
from file_organizer.formatting import describe_file, format_size
from file_organizer.history import NothingToUndo, undo_last_session
from file_organizer.service import apply_plan

_POLICIES = {
    "ask": None,
    "keep-both": Resolution.KEEP_BOTH,
    "replace": Resolution.REPLACE,
    "skip": Resolution.SKIP,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="file-organizer-cli",
        description="Sort the files of a folder into category subfolders.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    organize = commands.add_parser("organize", help="sort a folder")
    organize.add_argument("folder", type=Path)
    organize.add_argument(
        "-n", "--dry-run", action="store_true",
        help="show what would happen without moving anything",
    )
    organize.add_argument(
        "-y", "--yes", action="store_true", help="do not ask for confirmation"
    )
    organize.add_argument(
        "--on-conflict", choices=_POLICIES, default="ask",
        help="what to do when a file already exists at the destination "
             "(default: ask)",
    )
    organize.add_argument(
        "--include-hidden", action="store_true", help="also sort hidden files"
    )
    organize.add_argument(
        "--include-unknown", action="store_true",
        help=f"move unrecognized files into an '{OTHER_CATEGORY}' folder",
    )

    undo = commands.add_parser("undo", help="undo the last run in a folder")
    undo.add_argument("folder", type=Path)

    commands.add_parser("categories", help="list the supported file types")
    return parser


def _ask_resolver(total: int):
    """Return a resolver that asks the user on the terminal."""
    sticky: Resolution | None = None
    seen = 0
    choices = {"k": Resolution.KEEP_BOTH, "r": Resolution.REPLACE,
               "s": Resolution.SKIP}

    def resolver(move: PlannedMove) -> Resolution | None:
        nonlocal sticky, seen
        seen += 1
        if sticky is not None:
            if sticky is Resolution.REPLACE and not can_replace(move):
                return Resolution.KEEP_BOTH
            return sticky

        print(f"\nConflict {seen}/{total}: {move.source.name}")
        size, date = describe_file(move.source)
        print(f"  incoming: {move.source}  ({size}, {date})")
        replaceable = can_replace(move)
        if move.conflict is ConflictKind.EXISTS and move.existing:
            size, date = describe_file(move.existing)
            note = ""
            if replaceable and files_identical(move.source, move.existing):
                note = "  [identical content]"
            print(f"  existing: {move.existing}  ({size}, {date}){note}")
        else:
            print("  another file in this batch would get the same name")

        options = "[k]eep both  " + ("[r]eplace  " if replaceable else "")
        prompt = (
            f"  {options}[s]kip  [a]bort   "
            "(capital letter = apply to all remaining) > "
        )
        while True:
            try:
                answer = input(prompt).strip()
            except EOFError:
                return None
            letter = answer.lower()
            if letter == "a":
                return None
            if letter in choices and (letter != "r" or replaceable):
                decision = choices[letter]
                if answer.isupper():
                    sticky = decision
                return decision
            print("  Please answer k, r, s or a.")

    return resolver


def _print_plan(moves: Sequence[PlannedMove]) -> None:
    counts = Counter(move.category for move in moves)
    total_size = sum(move.size for move in moves)
    print(f"{len(moves)} file(s), {format_size(total_size)}:")
    for category, count in sorted(counts.items()):
        print(f"  {category:<14} {count}")
    conflicts = sum(1 for move in moves if move.conflict)
    if conflicts:
        print(f"{conflicts} conflict(s) to resolve.")


def _progress(done: int, total: int, _move: PlannedMove) -> None:
    if sys.stdout.isatty():
        print(f"\rMoving files... {done}/{total}", end="", flush=True)
        if done == total:
            print()


def _command_organize(args: argparse.Namespace) -> int:
    moves = plan_organization(
        args.folder,
        include_hidden=args.include_hidden,
        include_unknown=args.include_unknown,
    )
    if not moves:
        print("Nothing to organize.")
        return 0

    if args.dry_run:
        _print_plan(moves)
        for move in moves:
            flag = "  (conflict)" if move.conflict else ""
            print(f"  {move.source.name}  ->  {move.category}/{flag}")
        return 0

    _print_plan(moves)
    if not args.yes:
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("Cancelled. Nothing was changed.")
            return 130

    conflicts = sum(1 for move in moves if move.conflict)
    policy = _POLICIES[args.on_conflict]
    if policy is None:
        if conflicts and not sys.stdin.isatty():
            print(
                "error: conflicts found but no terminal to ask on; use "
                "--on-conflict keep-both|replace|skip",
                file=sys.stderr,
            )
            return 1
        resolver = _ask_resolver(conflicts)
    else:
        resolver = policy

    try:
        moves = resolve_conflicts(moves, resolver)
    except OperationCancelled:
        print("Cancelled. Nothing was changed.")
        return 130

    outcome = apply_plan(args.folder, moves, on_progress=_progress)
    print(f"Done: {outcome.count} file(s) moved.")
    if outcome.history_error:
        print(f"warning: undo history not saved: {outcome.history_error}",
              file=sys.stderr)
    elif outcome.count:
        print(f"Undo with: file-organizer-cli undo {args.folder}")
    return 0


def _command_undo(args: argparse.Namespace) -> int:
    report = undo_last_session(args.folder)
    print(f"Restored {report.restored} file(s).")
    for record, reason in report.skipped:
        print(f"  not restored: {record.destination.name} ({reason})")
    for warning in report.warnings:
        print(f"  warning: {warning}")
    return 0 if report.complete else 1


def _command_categories(_args: argparse.Namespace) -> int:
    for category, extensions in FILE_CATEGORIES.items():
        print(f"{category}: {' '.join(extensions)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {
        "organize": _command_organize,
        "undo": _command_undo,
        "categories": _command_categories,
    }
    try:
        return handlers[args.command](args)
    except (OSError, UnsafeFolderError, NothingToUndo) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OperationCancelled:
        print("Cancelled. Nothing was changed.")
        return 130
    except KeyboardInterrupt:
        print("\nInterrupted. Any partial work was rolled back.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
