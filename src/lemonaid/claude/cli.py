"""CLI commands for Claude Code integration."""

import argparse

from .notify import handle_dismiss, handle_notification


def cmd_notify(args: argparse.Namespace) -> None:
    """Handle Claude Code notification hook."""
    handle_notification()


def cmd_dismiss(args: argparse.Namespace) -> None:
    """Handle Claude Code dismiss hook (mark notification as read)."""
    handle_dismiss()


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
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
    notify_parser.set_defaults(func=cmd_notify)

    # claude dismiss
    dismiss_parser = claude_subparsers.add_parser(
        "dismiss",
        help="Mark session's notification as read (reads JSON from stdin)",
    )
    dismiss_parser.set_defaults(func=cmd_dismiss)

    claude_parser.set_defaults(func=lambda a: claude_parser.print_help())
