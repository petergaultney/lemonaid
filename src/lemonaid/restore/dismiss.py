"""`lemonaid restore dismiss`: say that lost or crashed lemons are not to come back."""

import argparse
import sys
from collections import abc

from ..audit import events
from ..inbox import db, ended
from . import auto, loss


def _matches(row: db.Notification, typed: str) -> bool:
    return (":" in typed and row.channel.startswith(typed)) or (
        row.name or ""
    ).casefold() == typed.casefold()


def chosen(
    lost: abc.Sequence[db.Notification], typed: abc.Sequence[str]
) -> tuple[list[db.Notification], list[str]]:
    """The lost rows *typed* names (a channel, its prefix, or the lemon's name), and the
    names that matched none.
    """
    return (
        [row for row in lost if any(_matches(row, each) for each in typed)],
        [each for each in typed if not any(_matches(row, each) for row in lost)],
    )


def cmd_dismiss(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        loss.mark(conn, by="restore dismiss")
        lost = [row for row in loss.candidates(conn) if ended.revivable(row.metadata)]
        rows, unknown = (lost, []) if args.all else chosen(lost, args.lemons)
        for row in rows:
            db.archive_channel(
                conn, row.channel, "restore dismiss", cause=ended.DISMISSED, by="user"
            )
            events.record("inbox-archive", row.channel, "restore dismiss")
            print(f"dismissed {row.name or row.channel}")

        auto.ask(conn, [row for row in loss.candidates(conn) if ended.lost(row.metadata)])

    for each in unknown:
        print(f"no lost lemon matches {each!r}", file=sys.stderr)
    if not rows and not unknown:
        print("No lemon is lost.")
    if unknown:
        sys.exit(1)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "dismiss",
        help="Archive lost or crashed lemons instead of restoring them",
        description="Marks lemons lost with their terminal server, or whose harness crashed, "
        "as dismissed and archives them, so no restore brings them back. Use it after killing "
        "a server or a lemon on purpose.",
    )
    parser.add_argument(
        "lemons", nargs="*", metavar="LEMON", help="A channel, channel prefix, or lemon name"
    )
    parser.add_argument("--all", action="store_true", help="Every lost lemon")
    parser.set_defaults(func=cmd_dismiss)
