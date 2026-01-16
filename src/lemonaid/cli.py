"""CLI entry point for lemonaid.

Lemonaid is a toolkit for working with lemons (LLMs). Current features:
- inbox: Attention management / notification inbox for tracking which lemons need you
"""

import argparse
import json
import sys
from datetime import datetime

from .config import ensure_config_exists, get_config_path
from .inbox import db


def cmd_inbox_list(args: argparse.Namespace) -> None:
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


def cmd_inbox_add(args: argparse.Namespace) -> None:
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


def cmd_inbox_read(args: argparse.Namespace) -> None:
    """Mark a notification as read."""
    with db.connect() as conn:
        db.mark_read(conn, args.id)
    print(f"Marked notification {args.id} as read")


def cmd_inbox_tui(args: argparse.Namespace) -> None:
    """Launch the inbox TUI."""
    from .inbox.tui import LemonaidApp

    app = LemonaidApp()
    app.run()


def cmd_config_init(args: argparse.Namespace) -> None:
    """Initialize config file with defaults."""
    config_path = ensure_config_exists()
    print(f"Config file at: {config_path}")


def cmd_config_path(args: argparse.Namespace) -> None:
    """Print config file path."""
    print(get_config_path())


def cmd_config_show(args: argparse.Namespace) -> None:
    """Show current config."""
    config_path = get_config_path()
    if config_path.exists():
        print(config_path.read_text())
    else:
        print(f"No config file at {config_path}")
        print("Run 'lemonaid config init' to create one.")


def cmd_claude_notify(args: argparse.Namespace) -> None:
    """Handle Claude Code notification hook."""
    from .claude.notify import handle_notification

    handle_notification()


def cmd_claude_dismiss(args: argparse.Namespace) -> None:
    """Handle Claude Code dismiss hook (mark notification as read)."""
    from .claude.notify import handle_dismiss

    handle_dismiss()


def cmd_wezterm_back(args: argparse.Namespace) -> None:
    """Switch back to the previous WezTerm location."""
    from . import wezterm

    if wezterm.go_back():
        pass  # Success - switched back
    else:
        print("No previous location saved", file=sys.stderr)
        sys.exit(1)


def setup_wezterm_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the wezterm subcommand."""
    wezterm_parser = subparsers.add_parser(
        "wezterm",
        help="WezTerm integration commands",
    )
    wezterm_subparsers = wezterm_parser.add_subparsers(dest="wezterm_command")

    # wezterm back
    back_parser = wezterm_subparsers.add_parser(
        "back",
        help="Switch back to previous location",
    )
    back_parser.set_defaults(func=cmd_wezterm_back)

    wezterm_parser.set_defaults(func=lambda a: wezterm_parser.print_help())


def setup_claude_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the claude subcommand."""
    claude_parser = subparsers.add_parser(
        "claude",
        help="Claude Code integration",
    )
    claude_subparsers = claude_parser.add_subparsers(dest="claude_command")

    # claude notify
    notify_parser = claude_subparsers.add_parser(
        "notify",
        help="Handle notification from Claude Code hook (reads JSON from stdin)",
    )
    notify_parser.set_defaults(func=cmd_claude_notify)

    # claude dismiss
    dismiss_parser = claude_subparsers.add_parser(
        "dismiss",
        help="Mark session's notification as read (reads JSON from stdin)",
    )
    dismiss_parser.set_defaults(func=cmd_claude_dismiss)

    claude_parser.set_defaults(func=lambda a: claude_parser.print_help())


def setup_config_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the config subcommand."""
    config_parser = subparsers.add_parser(
        "config",
        help="Manage lemonaid configuration",
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command")

    # config init
    init_parser = config_subparsers.add_parser("init", help="Create default config file")
    init_parser.set_defaults(func=cmd_config_init)

    # config path
    path_parser = config_subparsers.add_parser("path", help="Print config file path")
    path_parser.set_defaults(func=cmd_config_path)

    # config show
    show_parser = config_subparsers.add_parser("show", help="Show current config")
    show_parser.set_defaults(func=cmd_config_show)

    config_parser.set_defaults(func=cmd_config_show, config_command=None)


def setup_inbox_parser(subparsers: argparse._SubParsersAction) -> None:
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
    list_parser.set_defaults(func=cmd_inbox_list)

    # inbox add
    add_parser = inbox_subparsers.add_parser("add", help="Add a notification")
    add_parser.add_argument("channel", help="Channel/source identifier")
    add_parser.add_argument("title", help="Notification title")
    add_parser.add_argument("-m", "--message", help="Optional longer message")
    add_parser.add_argument("--metadata", help="JSON metadata for handlers")
    add_parser.set_defaults(func=cmd_inbox_add)

    # inbox read
    read_parser = inbox_subparsers.add_parser("read", help="Mark notification as read")
    read_parser.add_argument("id", type=int, help="Notification ID")
    read_parser.set_defaults(func=cmd_inbox_read)

    # Default for bare "lemonaid inbox" is TUI
    inbox_parser.set_defaults(func=cmd_inbox_tui, inbox_command=None)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="lemonaid",
        description="Toolkit for working with lemons (LLMs)",
    )
    subparsers = parser.add_subparsers(dest="command")

    setup_inbox_parser(subparsers)
    setup_claude_parser(subparsers)
    setup_wezterm_parser(subparsers)
    setup_config_parser(subparsers)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
    elif hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


def inbox_main() -> None:
    """Direct entry point for `lma` alias - goes straight to inbox TUI."""
    from .inbox.tui import LemonaidApp

    app = LemonaidApp()
    app.run()


if __name__ == "__main__":
    main()
