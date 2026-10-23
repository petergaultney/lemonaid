"""`inbox pin`, `inbox unpin`, `inbox archive`, `inbox unarchive`: the `lma` keys `P` and `Z`, and pin moves, by command."""

import argparse
import sqlite3

from . import db, decorate_cli, pins, unarchive

_MOVES = ("up", "down", "top", "bottom")


def _move(conn: sqlite3.Connection, channel: str, where: str) -> str:
    """Move a pin as `Shift`+`↑`/`↓` would; "" when it moved, else why it didn't."""
    if where in ("top", "bottom"):
        pins.move_to_edge(conn, channel, top=where == "top")
        return ""

    positions = pins.pinned_positions(conn)
    shown = [n.channel for n in db.get_active(conn) if n.channel in positions]
    if channel not in shown:
        return f"{channel} is pinned but not in the inbox (snoozed?), so it has no neighbour"

    neighbour = shown.index(channel) + (-1 if where == "up" else 1)
    if not 0 <= neighbour < len(shown):
        return f"{channel} is already the {'first' if where == 'up' else 'last'} pin"

    pins.swap(conn, channel, shown[neighbour])
    return ""


def _cmd_pin(args: argparse.Namespace) -> None:
    message = ""
    newly = False
    with db.connect() as conn:
        channel, error = decorate_cli.target_channel(conn, args)
        newest = db.get_by_channel(conn, channel, unread_only=False) if channel else None
        if newest and newest.is_archived:
            error = f"{channel} is archived; `inbox unarchive` it before pinning"

        if newest and not error:
            newly = not pins.is_pinned(conn, channel)
            if newly:
                pins.pin(conn, channel)

            if args.move:
                error = _move(conn, channel, args.move)
                message = f"Moved {channel} {args.move}"
            else:
                message = f"Pinned {channel}" if newly else f"{channel} was already pinned"

        pinned = bool(channel) and pins.is_pinned(conn, channel)

    if not error and not args.json:
        print(message)

    decorate_cli.finish(
        args, {"channel": channel or None, "pinned": pinned, "newly_pinned": newly}, error
    )


def _cmd_unpin(args: argparse.Namespace) -> None:
    removed = False
    with db.connect() as conn:
        channel, error = decorate_cli.target_channel(conn, args)
        if channel and not error:
            removed = pins.is_pinned(conn, channel)
            pins.unpin(conn, channel)

    if not error and not args.json:
        print(f"Unpinned {channel}" if removed else f"{channel} was not pinned")

    decorate_cli.finish(
        args, {"channel": channel or None, "pinned": False, "unpinned": removed}, error
    )


def _cmd_unarchive(args: argparse.Namespace) -> None:
    restored = 0
    with db.connect() as conn:
        channel, error = decorate_cli.target_channel(conn, args)
        newest = db.get_by_channel(conn, channel, unread_only=False) if channel else None
        if newest and not error:
            if newest.is_archived:
                restored = unarchive.restore(conn, channel)
            else:
                error = f"{channel} is not archived (it is {newest.status})"

    if not error and not args.json:
        print(f"Restored {channel} to the inbox, unread")

    decorate_cli.finish(args, {"channel": channel or None, "restored": restored > 0}, error)


def _cmd_archive(args: argparse.Namespace) -> None:
    archived = 0
    with db.connect() as conn:
        channel, error = decorate_cli.target_channel(conn, args)
        newest = db.get_by_channel(conn, channel, unread_only=False) if channel else None
        if newest and not error:
            if newest.is_archived:
                error = f"{channel} is already archived"
            else:
                db.archive(conn, newest.id, reason="inbox-archive-command")
                archived = 1

    if not error and not args.json:
        print(f"Archived {channel}")

    decorate_cli.finish(args, {"channel": channel or None, "archived": archived > 0}, error)


def add_parsers(inbox_subparsers: argparse._SubParsersAction) -> None:
    pin = inbox_subparsers.add_parser(
        "pin",
        help="Pin a session below any other pins, or reorder pins with --move",
        description="Holds a session at its place above the unpinned ones, like the TUI's "
        "P key. Already pinned is a no-op that exits 0. --move orders pins like Shift+Up and "
        "Shift+Down: up and down trade places with the neighbouring pin as the inbox lists "
        "them; top and bottom put it above or below every other pin. A pin is keyed by "
        "channel, and archiving a session drops its pin.",
        epilog="Examples:\n"
        "  lemonaid inbox pin --lemon hq.LemonAce\n"
        "  lemonaid inbox pin --channel claude:1a2b3c4d --move top",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    decorate_cli.add_target(pin)
    pin.add_argument("--move", choices=_MOVES, help="Reorder the pin (pins it first if needed)")
    pin.set_defaults(func=_cmd_pin)

    unpin = inbox_subparsers.add_parser(
        "unpin",
        help="Remove a session's pin",
        description="Releases a pin. A session that is not pinned is a no-op that exits 0.",
    )
    decorate_cli.add_target(unpin)
    unpin.set_defaults(func=_cmd_unpin)

    unarchive_parser = inbox_subparsers.add_parser(
        "unarchive",
        help="Restore an archived session to the inbox",
        description="Makes every archived row on the session's channel unread again and its "
        "newest row newest on its tty, as resuming it from history does. It does not "
        "restart the harness, reattach a brief, or restore the pin that archiving dropped. "
        "The watcher archives it again if its pane is gone. Refuses a session that is not "
        "archived.",
    )
    decorate_cli.add_target(unarchive_parser)
    unarchive_parser.set_defaults(func=_cmd_unarchive)

    archive_parser = inbox_subparsers.add_parser(
        "archive",
        help="Remove a session's card from the inbox",
        description="Archives every row on the session's channel and drops its pin, like the "
        "TUI's archive key. It does not stop the harness or touch its brief. `inbox unarchive` "
        "restores it. Refuses a session that is already archived.",
        epilog="Example:\n  lemonaid inbox archive --id 2306",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    decorate_cli.add_target(archive_parser)
    archive_parser.set_defaults(func=_cmd_archive)
