"""CLI commands for the inbox."""

import argparse
import json
import sys
from datetime import datetime

from . import db


def cmd_list(args: argparse.Namespace) -> None:
    """List unread notifications."""
    with db.connect() as conn:
        notifications = db.get_unread(conn)

    if not notifications:
        print("No unread notifications.")
        return

    for n in notifications:
        created = datetime.fromtimestamp(n.created_at).strftime("%H:%M:%S")
        print(f"[{n.id}] {created} | {n.channel} | {n.title}")
        if args.verbose and n.message:
            print(f"    {n.message}")


def cmd_add(args: argparse.Namespace) -> None:
    """Add a notification."""
    metadata = None
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as e:
            print(f"Error: invalid JSON metadata: {e}", file=sys.stderr)
            sys.exit(1)

    with db.connect() as conn:
        notification = db.add(
            conn,
            channel=args.channel,
            title=args.title,
            message=args.message,
            metadata=metadata,
        )
    print(f"Added notification {notification.id}")


def cmd_read(args: argparse.Namespace) -> None:
    """Mark a notification as read."""
    with db.connect() as conn:
        db.mark_read(conn, args.id)
    print(f"Marked notification {args.id} as read")


def cmd_tui(args: argparse.Namespace) -> None:
    """Launch the inbox TUI."""
    from .tui import LemonaidApp

    app = LemonaidApp()
    app.run()


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the inbox subcommand and its sub-subcommands."""
    inbox_parser = subparsers.add_parser(
        "inbox",
        help="Attention inbox - track notifications from lemons",
        description="Manage notifications from Claude Code and other tools",
    )
    inbox_subparsers = inbox_parser.add_subparsers(dest="inbox_command")

    # inbox list
    list_parser = inbox_subparsers.add_parser("list", aliases=["ls"], help="List unread")
    list_parser.add_argument("-v", "--verbose", action="store_true", help="Show full messages")
    list_parser.set_defaults(func=cmd_list)

    # inbox add
    add_parser = inbox_subparsers.add_parser("add", help="Add a notification")
    add_parser.add_argument("channel", help="Channel/source identifier")
    add_parser.add_argument("title", help="Notification title")
    add_parser.add_argument("-m", "--message", help="Optional longer message")
    add_parser.add_argument("--metadata", help="JSON metadata for handlers")
    add_parser.set_defaults(func=cmd_add)

    # inbox read
    read_parser = inbox_subparsers.add_parser("read", help="Mark notification as read")
    read_parser.add_argument("id", type=int, help="Notification ID")
    read_parser.set_defaults(func=cmd_read)

    # Default for bare "lemonaid inbox" is TUI
    inbox_parser.set_defaults(func=cmd_tui, inbox_command=None)
