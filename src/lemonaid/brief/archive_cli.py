import argparse
import sqlite3
import sys
import time
from pathlib import Path

from ..inbox import db
from . import archive, identity, lemon, store

_CHANNEL = "lemonaid:brief-sweep"


def _brief(conn, target: str) -> Path:
    if identity.valid(target) and (path := lemon.brief_of(conn, target)) is not None:
        return path

    path = store.resolve(target)
    if error := store.outside_error(path):
        raise LookupError(error)

    if not path.is_file():
        raise LookupError(f"No brief at {path}")

    return path


def _too_many(conn: sqlite3.Connection, found: int, days: float, most: int) -> int:
    """Say in the inbox that the sweep moved nothing, since more than *most* looked idle."""
    line = (
        f"The brief sweep found {found} briefs unused for {days:g}+ days, more than the {most} "
        "it may move at once (`[brief] archive_sweep_max`), so it moved none. "
        f"`lemonaid brief archive --idle-days {days:g} --dry-run` lists them, and the same "
        "command without --dry-run moves them."
    )
    print(line, file=sys.stderr)
    db.add(conn, _CHANNEL, line, name="brief sweep")
    return 1


def _sweep(days: float, dry_run: bool, most: int) -> int:
    with db.connect() as conn:
        found = archive.idle(conn, days, time.time())
        if most and len(found) > most and not dry_run:
            return _too_many(conn, len(found), days, most)

        failed = 0
        for item in found:
            used = time.strftime("%Y-%m-%d", time.localtime(item.last)) if item.last else "never"
            if dry_run:
                print(f"{item.path.name}  (last used {used})")
                continue

            try:
                print(
                    f"{item.path.name} -> {archive.archive(conn, item.path, item.last, why=f'idle sweep: unused {days:g}+ days')}"
                )
            except (OSError, ValueError, sqlite3.Error) as error:
                failed += 1
                print(f"{item.path.name}: not archived: {error}", file=sys.stderr)
    verb = "would be archived" if dry_run else "archived"
    print(f"{len(found) - failed} brief(s) idle for {days:g}+ days {verb}")
    return 1 if failed else 0


def _cmd_archive(args: argparse.Namespace) -> None:
    if (args.target is None) == (args.idle_days is None):
        print("Name one brief, or give --idle-days", file=sys.stderr)
        sys.exit(2)

    if args.idle_days is not None:
        sys.exit(_sweep(args.idle_days, args.dry_run, args.most))

    with db.connect() as conn:
        try:
            path = _brief(conn, args.target)
            last = archive.last_used(conn, path)
            if args.dry_run:
                print(f"{path} would be archived")
                return

            print(archive.archive(conn, path, min(last, time.time()), why="by hand"))
        except (LookupError, OSError, ValueError) as error:
            print(f"Not archived: {error}", file=sys.stderr)
            sys.exit(1)


def _cmd_revive(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            print(archive.revive(conn, lemon.current(conn, args.lemon_id), why="by hand"))
        except (LookupError, OSError, ValueError) as error:
            print(f"Not revived: {error}", file=sys.stderr)
            sys.exit(1)


def add_parsers(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "archive",
        help="Move a brief, or every brief unused for --idle-days, and its mailbox to the attic",
    )
    parser.add_argument("target", nargs="?", help="A Lemon-ID, or a brief's name or path")
    parser.add_argument(
        "--idle-days", type=float, help="Archive every brief nobody has used for this many days"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=0,
        dest="most",
        help="With --idle-days, move nothing when more briefs than this are idle (0: no limit)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List what would move")
    parser.set_defaults(func=_cmd_archive)

    revive = subparsers.add_parser(
        "revive", help="Move an archived brief and its mailbox back, unattached"
    )
    revive.add_argument("lemon_id")
    revive.set_defaults(func=_cmd_revive)
