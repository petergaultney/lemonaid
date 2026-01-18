"""CLI commands for the inbox."""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime

from . import db


def _notification_to_json(n: db.Notification) -> dict:
    """Convert notification to JSON-serializable dict."""
    return asdict(n)


def cmd_list(args: argparse.Namespace) -> None:
    """List unread notifications."""
    with db.connect() as conn:
        notifications = db.get_unread(conn)

    if getattr(args, "json", False):
        print(json.dumps([_notification_to_json(n) for n in notifications]))
        return

    if not notifications:
        print("No unread notifications.")
        return

    for n in notifications:
        created = datetime.fromtimestamp(n.created_at).strftime("%H:%M:%S")
        name_part = f" ({n.name})" if n.name else ""
        print(f"[{n.id}] {created} | {n.channel}{name_part} | {n.message}")


def cmd_get(args: argparse.Namespace) -> None:
    """Get a specific notification by ID."""
    with db.connect() as conn:
        notification = db.get(conn, args.id)

    if notification is None:
        if getattr(args, "json", False):
            print("null")
        else:
            print(f"Notification {args.id} not found", file=sys.stderr)
            sys.exit(1)
        return

    if getattr(args, "json", False):
        print(json.dumps(_notification_to_json(notification)))
    else:
        created = datetime.fromtimestamp(notification.created_at).strftime("%Y-%m-%d %H:%M:%S")
        print(f"ID:      {notification.id}")
        print(f"Channel: {notification.channel}")
        if notification.name:
            print(f"Name:    {notification.name}")
        print(f"Message: {notification.message}")
        print(f"Status:  {notification.status}")
        print(f"Created: {created}")


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
            message=args.message,
            name=args.name,
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
    list_parser.add_argument("--json", action="store_true", help="Output as JSON (for lemons)")
    list_parser.set_defaults(func=cmd_list)

    # inbox get
    get_parser = inbox_subparsers.add_parser("get", help="Get a notification by ID")
    get_parser.add_argument("id", type=int, help="Notification ID")
    get_parser.add_argument("--json", action="store_true", help="Output as JSON (for lemons)")
    get_parser.set_defaults(func=cmd_get)

    # inbox add
    add_parser = inbox_subparsers.add_parser("add", help="Add a notification")
    add_parser.add_argument("channel", help="Channel/source identifier")
    add_parser.add_argument("message", help="Notification message")
    add_parser.add_argument("-n", "--name", help="Optional session name")
    add_parser.add_argument("--metadata", help="JSON metadata for handlers")
    add_parser.set_defaults(func=cmd_add)

    # inbox read
    read_parser = inbox_subparsers.add_parser("read", help="Mark notification as read")
    read_parser.add_argument("id", type=int, help="Notification ID")
    read_parser.set_defaults(func=cmd_read)

    # Default for bare "lemonaid inbox" is TUI
    inbox_parser.set_defaults(func=cmd_tui, inbox_command=None)
