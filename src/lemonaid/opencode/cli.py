"""CLI commands for OpenCode integration."""

import argparse

from .notify import _dismiss_session, handle_dismiss, handle_notification


def cmd_notify(args: argparse.Namespace) -> None:
    """Handle OpenCode notification hook."""
    handle_notification(
        stdin_data=args.payload,
        session_id=args.session_id,
        cwd=args.cwd,
        name=args.name,
        message=args.message,
        notification_type=args.notification_type,
    )


def cmd_dismiss(args: argparse.Namespace) -> None:
    """Handle OpenCode dismiss hook (mark notification as read)."""
    if args.session_id:
        _dismiss_session(args.session_id)
    else:
        handle_dismiss()


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the opencode subcommand."""
    opencode_parser = subparsers.add_parser(
        "opencode",
        help="OpenCode integration",
    )
    opencode_subparsers = opencode_parser.add_subparsers(dest="opencode_command")

    notify_parser = opencode_subparsers.add_parser(
        "notify",
        help="Handle notification from OpenCode plugin hook",
    )
    notify_parser.add_argument(
        "payload",
        nargs="?",
        help="JSON payload from OpenCode plugin event",
    )
    notify_parser.add_argument(
        "--session-id",
        "-s",
        help="OpenCode session ID",
    )
    notify_parser.add_argument(
        "--cwd",
        help="Working directory for the session",
    )
    notify_parser.add_argument(
        "--name",
        help="Display name for the session",
    )
    notify_parser.add_argument(
        "--message",
        help="Notification message override",
    )
    notify_parser.add_argument(
        "--notification-type",
        help="Notification/event type (e.g., session.idle, permission.asked)",
    )
    notify_parser.set_defaults(func=cmd_notify)

    dismiss_parser = opencode_subparsers.add_parser(
        "dismiss",
        help="Mark session's notification as read (reads JSON from stdin)",
    )
    dismiss_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to dismiss (if not provided, reads from stdin)",
    )
    dismiss_parser.set_defaults(func=cmd_dismiss)

    opencode_parser.set_defaults(func=lambda a: opencode_parser.print_help())
