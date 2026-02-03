"""CLI commands for OpenClaw integration."""

import argparse

from .notify import dismiss_session, handle_dismiss, handle_notification, handle_register


def cmd_notify(args: argparse.Namespace) -> None:
    """Handle OpenClaw notification hook."""
    handle_notification(
        stdin_data=args.payload,
        session_id=args.session_id,
        agent_id=args.agent_id,
        session_path=args.session_path,
        cwd=args.cwd,
        name=args.name,
        message=args.message,
        notification_type=args.notification_type,
    )


def cmd_dismiss(args: argparse.Namespace) -> None:
    """Handle OpenClaw dismiss hook (mark notification as read)."""
    if args.session_id:
        dismiss_session(args.session_id)
    else:
        handle_dismiss()


def cmd_register(args: argparse.Namespace) -> None:
    """Register current OpenClaw session with lemonaid (captures TTY)."""
    success = handle_register(session_id=args.session_id, cwd=args.cwd)
    if not success:
        raise SystemExit(1)


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Set up the openclaw subcommand."""
    openclaw_parser = subparsers.add_parser(
        "openclaw",
        help="OpenClaw integration",
    )
    openclaw_subparsers = openclaw_parser.add_subparsers(dest="openclaw_command")

    notify_parser = openclaw_subparsers.add_parser(
        "notify",
        help="Handle notification from OpenClaw hook (reads JSON from stdin)",
    )
    notify_parser.add_argument(
        "payload",
        nargs="?",
        help="JSON payload from OpenClaw hook (passed as a single argument)",
    )
    notify_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to associate with the notification",
    )
    notify_parser.add_argument(
        "--agent-id",
        "-a",
        help="Agent ID (if known)",
    )
    notify_parser.add_argument(
        "--session-path",
        help="Path to OpenClaw session jsonl file",
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
        help="Notification/event type",
    )
    notify_parser.set_defaults(func=cmd_notify)

    dismiss_parser = openclaw_subparsers.add_parser(
        "dismiss",
        help="Mark session's notification as read (reads JSON from stdin)",
    )
    dismiss_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to dismiss (if not provided, reads from stdin)",
    )
    dismiss_parser.set_defaults(func=cmd_dismiss)

    register_parser = openclaw_subparsers.add_parser(
        "register",
        help="Register session with lemonaid (run from TUI: !lemonaid openclaw register)",
    )
    register_parser.add_argument(
        "--session-id",
        "-s",
        help="Session ID to register (default: most recently modified session)",
    )
    register_parser.add_argument(
        "--cwd",
        help="Override cwd (default: use session's cwd from header)",
    )
    register_parser.set_defaults(func=cmd_register)

    openclaw_parser.set_defaults(func=lambda a: openclaw_parser.print_help())
