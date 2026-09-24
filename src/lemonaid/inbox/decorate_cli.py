"""`inbox rename`, `inbox emoji`, `inbox emojis`: decorate a harness session.

Every target resolves to one inbox channel - the backend session, which is the
actor - before anything changes. `--self` is the convenience form and refuses
rather than guesses; see `self_session`. The rename is the same user override
the TUI's rename key sets, applied to the channel's newest row.
"""

import argparse
import json
import os
import sqlite3
import sys

from . import db, emoji, self_session


def _channel(conn: sqlite3.Connection, args: argparse.Namespace) -> tuple[str, str]:
    """(channel, "") for the session the arguments name, else ("", why not)."""
    if args.id is not None:
        found = db.get(conn, args.id)
        return (found.channel, "") if found else ("", f"No notification {args.id}")

    if args.channel:
        found = db.get_by_channel(conn, args.channel, unread_only=False)
        return (found.channel, "") if found else ("", f"No inbox session {args.channel!r}")

    pane_id = os.environ.get("TMUX_PANE", "")
    if not pane_id:
        return "", "Not inside tmux ($TMUX_PANE unset), so there is no session to call self"

    where = self_session.pane_location(pane_id)
    if where is None:
        return "", f"Could not ask tmux where pane {pane_id} is"

    return self_session.resolve(conn, where)


def _finish(args: argparse.Namespace, result: dict, error: str) -> None:
    if args.json:
        print(json.dumps({**result, "error": error or None}, ensure_ascii=False))
    elif error:
        print(error, file=sys.stderr)

    if error:
        sys.exit(1)


def _cmd_rename(args: argparse.Namespace) -> None:
    name = "" if args.clear else args.name.strip()
    renamed: db.Notification | None = None
    with db.connect() as conn:
        channel, error = _channel(conn, args)
        if channel and not args.clear and not name:
            error = "Give a name, or --clear"

        newest = db.get_by_channel(conn, channel, unread_only=False) if channel else None
        if newest and not error:
            db.update_name(conn, newest.id, name or None)
            renamed = db.get(conn, newest.id)

    _finish(
        args,
        {"channel": channel or None, "name": renamed.name if renamed else None},
        error,
    )


def _cmd_emoji(args: argparse.Namespace) -> None:
    value = "" if args.clear else args.emoji.strip()
    with db.connect() as conn:
        channel, error = _channel(conn, args)
        if channel and not args.clear and not value:
            error = "Give an emoji, or --clear"

        if channel and value and not error and (held := emoji.holder(conn, value, channel)):
            error = (
                f"{value} is already held by live session {held['channel']} "
                f"({held['name'] or 'unnamed'}); pick another. "
                "`lemonaid inbox emojis --json` lists the ones in use."
            )

        if channel and not error:
            if value:
                emoji.set_emoji(conn, channel, value)
            else:
                emoji.clear(conn, channel)

    _finish(args, {"channel": channel or None, "emoji": value}, error)


def _cmd_emojis(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        held = emoji.in_use(conn)

    if args.json:
        print(json.dumps(held, ensure_ascii=False))
        return

    for entry in held:
        print(f"{entry['emoji']}  {entry['channel']} {entry['name'] or ''}".rstrip())


def _add_target(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--self",
        dest="use_self",
        action="store_true",
        help="The live session recorded at this tmux pane's tty, session, and window; "
        "refuses if there is not exactly one",
    )
    target.add_argument("--id", type=int, help="The session a notification id belongs to")
    target.add_argument("--channel", help="An inbox channel, e.g. claude:1a2b3c4d")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")


def add_parsers(inbox_subparsers: argparse._SubParsersAction) -> None:
    rename = inbox_subparsers.add_parser(
        "rename",
        help="Set or clear a session's display name",
        description="Sets the name the inbox shows for a session, like the TUI's "
        "rename key. It never changes the tmux session name. --clear restores the "
        "name the backend gave it.",
        epilog="Examples:\n"
        '  lemonaid inbox rename --self "tenant views"\n'
        "  lemonaid inbox rename --channel claude:1a2b3c4d --clear",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_target(rename)
    rename.add_argument("name", nargs="?", default="", help="The new display name")
    rename.add_argument("--clear", action="store_true", help="Restore the backend's name")
    rename.set_defaults(func=_cmd_rename)

    emoji_parser = inbox_subparsers.add_parser(
        "emoji",
        help="Set or clear the emoji shown before a session's name",
        description="Marks one harness session (a Claude session or Codex thread), "
        "not its place or tmux session. It survives compaction and resume. An emoji "
        "another live session holds is refused; `inbox emojis` lists them.",
        epilog="Examples:\n  lemonaid inbox emoji --self 🦫\n  lemonaid inbox emoji --self --clear",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_target(emoji_parser)
    emoji_parser.add_argument("emoji", nargs="?", default="", help="The emoji to show")
    emoji_parser.add_argument("--clear", action="store_true", help="Remove the emoji")
    emoji_parser.set_defaults(func=_cmd_emoji)

    emojis_parser = inbox_subparsers.add_parser(
        "emojis",
        help="List the emojis live sessions hold",
        description="Every emoji shown by a live (unarchived, including snoozed) "
        "session, with its channel, name, and cwd. `inbox emoji` refuses these.",
    )
    emojis_parser.add_argument("--json", action="store_true", help="Print the list as JSON")
    emojis_parser.set_defaults(func=_cmd_emojis)
