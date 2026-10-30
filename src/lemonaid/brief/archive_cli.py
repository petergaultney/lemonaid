import argparse
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from ..config import load_config
from ..inbox import db
from ..log import LOG_PATH, get_logger
from ..watch import reconcile, registry
from . import archive, identity, lemon, store

_log = get_logger("brief.archive_cli")
_DAILY_SECONDS = 24 * 60 * 60
COMMANDS = frozenset({"archive", "revive"})  # `brief` subcommands that start no daily sweep


def _brief(conn, target: str) -> Path:
    if identity.valid(target) and (path := lemon.brief_of(conn, target)) is not None:
        return path

    path = store.resolve(target)
    if error := store.outside_error(path):
        raise LookupError(error)

    if not path.is_file():
        raise LookupError(f"No brief at {path}")

    return path


def _sweep(days: float, dry_run: bool) -> int:
    with db.connect() as conn:
        found = archive.idle(conn, days, time.time())
        failed = 0
        for item in found:
            used = time.strftime("%Y-%m-%d", time.localtime(item.last)) if item.last else "never"
            if dry_run:
                print(f"{item.path.name}  (last used {used})")
                continue

            try:
                print(f"{item.path.name} -> {archive.archive(conn, item.path, item.last)}")
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
        sys.exit(_sweep(args.idle_days, args.dry_run))

    with db.connect() as conn:
        try:
            path = _brief(conn, args.target)
            last = archive.last_used(conn, path)
            if args.dry_run:
                print(f"{path} would be archived")
                return

            print(archive.archive(conn, path, min(last, time.time())))
        except (LookupError, OSError, ValueError) as error:
            print(f"Not archived: {error}", file=sys.stderr)
            sys.exit(1)


def _cmd_revive(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        try:
            print(archive.revive(conn, lemon.current(conn, args.lemon_id)))
        except (LookupError, OSError, ValueError) as error:
            print(f"Not revived: {error}", file=sys.stderr)
            sys.exit(1)


def _stamp() -> Path:
    return registry.root() / "brief-archive-sweep"


def daily() -> None:
    """Start a background sweep under `[brief] archive_idle_days`, at most once a day."""
    days = load_config().brief.archive_idle_days
    try:
        if not days or time.time() - _stamp().stat().st_mtime < _DAILY_SECONDS:
            return
    except FileNotFoundError:
        pass
    if reconcile.editable_install():
        return

    _stamp().parent.mkdir(parents=True, exist_ok=True)
    _stamp().touch()
    try:
        with LOG_PATH.open("a") as log:
            subprocess.Popen(
                [sys.executable, "-m", "lemonaid", "brief", "archive", "--idle-days", str(days)],
                env={k: v for k, v in os.environ.items() if k != "CODEX_THREAD_ID"},
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
    except OSError as error:
        _log.warning("could not start the brief archive sweep: %s", error)


def add_parsers(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "archive",
        help="Move a brief, or every brief unused for --idle-days, and its inbox to the attic",
    )
    parser.add_argument("target", nargs="?", help="A Lemon-ID, or a brief's name or path")
    parser.add_argument(
        "--idle-days", type=float, help="Archive every brief nobody has used for this many days"
    )
    parser.add_argument("--dry-run", action="store_true", help="List what would move")
    parser.set_defaults(func=_cmd_archive)

    revive = subparsers.add_parser(
        "revive", help="Move an archived brief and its inbox back, unattached"
    )
    revive.add_argument("lemon_id")
    revive.set_defaults(func=_cmd_revive)
