"""`lemonaid home migrate`: move briefs and messages to `~/.lemons/`."""

import argparse
import json
import os
import sys

from ..inbox import db
from . import inventory, migrate, reconcile, rollback

_PINNED = ("LEMONAID_BRIEFS_DIR", "LEMONAID_MESSAGES_DIR")


def _cmd_migrate(args: argparse.Namespace) -> None:
    pinned = [name for name in _PINNED if os.environ.get(name)]
    if pinned:
        print(
            f"{', '.join(pinned)} pins briefs or messages to one folder, so there is no "
            "home to migrate; unset it to move LEMONAID_LEGACY_BRIEFS_DIR to LEMONAID_LEMONS_DIR",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.dry_run:
        with db.connect() as conn:
            found = inventory.plan(conn)
        if args.json:
            print(inventory.to_json(found))
        else:
            files = sum(not e.directory for e in found.entries)
            print(f"{found.old} -> {found.new_briefs} and {found.new_inbox}")
            print(f"{files} files, DB rows: {found.db_rows or 'none'}")
            print(f"Armed inbox waiters: {', '.join(found.armed) or 'none'}")
            print("\n".join(["Blockers:", *found.blockers]) if found.blockers else "No blockers")
        sys.exit(1 if found.blockers else 0)

    outcome = (
        rollback.run
        if args.rollback
        else migrate.abort
        if args.abort
        else migrate.pause
        if args.pause
        else reconcile.run
        if args.reconcile
        else migrate.run
    )()
    if args.json:
        print(
            json.dumps(
                {"done": outcome.done, "paused": outcome.paused, "messages": outcome.messages}
            )
        )
    else:
        print("\n".join(outcome.messages), file=sys.stdout if outcome.done else sys.stderr)
    sys.exit(0 if outcome.done or (args.abort and not outcome.paused) else 1)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("home", help="Where briefs and messages live")
    home_subparsers = parser.add_subparsers(dest="home_command", required=True)
    migrate_parser = home_subparsers.add_parser(
        "migrate",
        help="Move ~/.brief-lemons/ to ~/.lemons/brief/ and ~/.lemons/inbox/",
        description="Copies every brief and message, checks each copy, rewrites the "
        "database's brief paths, and moves the old home aside as a backup. Brief and "
        "message commands wait while it runs. It refuses, changing nothing, while an "
        "inbox waiter or the Codex delivery service is running, or when anything "
        "would be overwritten. Rerun to continue after a stop. See docs/home.md.",
    )
    mode = migrate_parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="Show what would move and what blocks it"
    )
    mode.add_argument(
        "--pause",
        action="store_true",
        help="Only pause brief and message commands, so waiters can be stopped first",
    )
    mode.add_argument(
        "--reconcile",
        action="store_true",
        help="Move files written to ~/.brief-lemons/ after cutover into ~/.lemons/",
    )
    mode.add_argument(
        "--abort", action="store_true", help="Undo a migration stopped before its move"
    )
    mode.add_argument(
        "--rollback",
        action="store_true",
        help="Return to ~/.brief-lemons/ if nothing changed since",
    )
    migrate_parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    migrate_parser.set_defaults(func=_cmd_migrate)
