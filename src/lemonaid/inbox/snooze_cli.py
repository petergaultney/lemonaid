"""`inbox snooze`: snooze a session from the command line, most often a lemon's own.

It takes the TUI snooze picker's syntax (`snooze_time`). Unlike a TUI snooze, it
lasts through the session's turn ends: a lemon snoozing itself is mid-turn, and
the end of that turn would otherwise wake it straight away. A permission prompt
or a question still wakes it, as does `--clear` or the TUI.
"""

import argparse
import time
from datetime import datetime

from . import db, decorate_cli, snooze_time


def _summary(channel: str, wakes: str | None, woke: bool) -> str:
    if wakes:
        return f"Snoozed {channel} until {wakes}"

    return f"Woke {channel}" if woke else f"{channel} was not snoozed"


def _cmd_snooze(args: argparse.Namespace) -> None:
    now = time.time()
    until = None if args.clear else snooze_time.parse_wake(args.when, now)
    woke = False
    with db.connect() as conn:
        db.wake_expired(conn, now)
        channel, error = decorate_cli.target_channel(conn, args)
        newest = db.get_by_channel(conn, channel, unread_only=False) if channel else None
        if newest and not error:
            if args.clear:
                woke = db.unsnooze(conn, channel) > 0
            elif until is None:
                error = f"Give {snooze_time.SYNTAX} (or --clear to wake it)"
            elif newest.is_archived:
                error = f"{channel} is archived, so there is nothing to snooze"
            else:
                db.snooze(conn, newest.id, until, through_turns=True)

    until = None if error else until
    wakes = datetime.fromtimestamp(until).isoformat(timespec="minutes") if until else None
    if not args.json and not error:
        print(_summary(channel, wakes, woke))

    decorate_cli.finish(
        args,
        {"channel": channel or None, "snooze_until": until, "wakes": wakes, "woke": woke},
        error,
    )


def add_parser(inbox_subparsers: argparse._SubParsersAction) -> None:
    parser = inbox_subparsers.add_parser(
        "snooze",
        help="Snooze a session out of the inbox, or wake it with --clear",
        description="Holds a session out of the active inbox until WHEN, like the TUI's "
        "snooze key, and takes the same syntax: a duration (45m, 2h, 3d; a bare number "
        "is minutes) or 'morning' (the next 9am). Unlike a TUI snooze it lasts through "
        "the session's turn ends, and it wakes unread if any of those turns ended unread. "
        "A permission prompt or a question wakes it early. Snoozing a snoozed session "
        "moves its wake time.",
        epilog="Examples:\n"
        "  lemonaid inbox snooze --self 2h\n"
        "  lemonaid inbox snooze --self morning\n"
        "  lemonaid inbox snooze --self --clear",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    decorate_cli.add_target(parser)
    parser.add_argument("when", nargs="?", default="", help="45m, 2h, 3d, or morning")
    parser.add_argument("--clear", action="store_true", help="Wake the session now")
    parser.set_defaults(func=_cmd_snooze)
