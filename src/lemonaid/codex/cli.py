"""CLI commands for Codex CLI integration."""

import argparse

from .notify import dismiss_session, handle_dismiss, handle_notification


def cmd_notify(args: argparse.Namespace) -> None:
    """Handle Codex CLI notification hook."""
    handle_notification(
        stdin_data=args.payload,
        session_id=args.session_id,
        session_path=args.session_path,
        cwd=args.cwd,
        name=args.name,
        message=args.message,
        notification_type=args.notification_type,
    )


def cmd_dismiss(args: argparse.Namespace) -> None:
    """Handle Codex CLI dismiss hook (mark notification as read)."""
    if args.session_id:
        dismiss_session(args.session_id)
    else:
        handle_dismiss()


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the codex subcommand."""
    codex_parser = subparsers.add_parser(
        "codex",
        help="Codex CLI integration",
    )
    codex_subparsers = codex_parser.add_subparsers(dest="codex_command")

    notify_parser = codex_subparsers.add_parser(
        "notify",
        help="Handle notification from Codex CLI notify hook (reads JSON from stdin)",
    )
    notify_parser.add_argument(
        "payload",
        nargs="?",
        help="JSON payload from Codex notify hook (passed as a single argument)",
    )
    notify_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to associate with the notification",
    )
    notify_parser.add_argument(
        "--session-path",
        help="Path to Codex session jsonl file",
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
        help="Notification/event type (e.g., agent-turn-complete)",
    )
    notify_parser.set_defaults(func=cmd_notify)

    dismiss_parser = codex_subparsers.add_parser(
        "dismiss",
        help="Mark session's notification as read (reads JSON from stdin)",
    )
    dismiss_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to dismiss (if not provided, reads from stdin)",
    )
    dismiss_parser.set_defaults(func=cmd_dismiss)

    codex_parser.set_defaults(func=lambda a: codex_parser.print_help())
